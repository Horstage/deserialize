"""A module for deserializing data to Python objects."""

# pylint: disable=unidiomatic-typecheck
# pylint: disable=protected-access
# pylint: disable=too-many-branches
# pylint: disable=wildcard-import

import enum
import functools
import typing
from typing import Any, Callable, Dict, List, Optional, Union

from deserialize.decorators import (
    ignore,
    _should_ignore,
    key,
    _get_key,
    parser,
    _get_parser,
)
from deserialize.exceptions import (
    DeserializeException,
    InvalidBaseTypeException,
    UnhandledFieldException,
)
from deserialize.type_checks import *

# pylint: disable=function-redefined
def deserialize(class_reference, data, throw_on_unhandled: bool = False, strict=True):
    """Deserialize data to a Python object."""

    if not isinstance(data, dict) and not isinstance(data, list):
        raise InvalidBaseTypeException(
            "Only lists and dictionaries are supported as base raw data types"
        )

    try:
        name = class_reference.__name__
    except AttributeError:
        name = str(class_reference)

    return _deserialize(class_reference, data, name, throw_on_unhandled=throw_on_unhandled, strict=strict)


# pylint: enable=function-redefined


def _deserialize(class_reference, data, debug_name, throw_on_unhandled: bool, strict):
    """Deserialize data to a Python object, but allow base types"""

    if class_reference == Any:
        return data

    if is_union(class_reference):
        valid_types = union_types(class_reference)
        for valid_type in valid_types:
            try:
                return _deserialize(valid_type, data, debug_name, throw_on_unhandled, strict)
            except DeserializeException:
                pass
        raise DeserializeException(
            f"Cannot deserialize '{type(data)}' to '{class_reference}' for '{debug_name}'"
        )

    if isinstance(data, dict):
        return _deserialize_dict(class_reference, data, debug_name, throw_on_unhandled, strict)

    if isinstance(data, list):
        return _deserialize_list(class_reference, data, debug_name, throw_on_unhandled, strict)

    if isinstance(data, tuple) and is_typing_type(class_reference):
        return _deserialize_tuple(class_reference, data, debug_name, throw_on_unhandled, strict)

    if not is_typing_type(class_reference) and issubclass(class_reference, enum.Enum):
        try:
            return class_reference(data)
        # pylint:disable=bare-except
        except:
            # pylint:enable=bare-except
            # This will be handled at the end
            pass

    # If we still have a type from the typing module, we don't know how to
    # handle it
    if is_typing_type(class_reference):
        # The data should not be None if we have a type that got here. Optionals
        # are handled by unions above, so if we are here, it's a non-optional
        # type and therefore should not be None.
        if data is None:
            raise DeserializeException(
                f"No value for '{debug_name}'. Expected value of type '{class_reference}'"
            )

        raise DeserializeException(f"Unsupported deserialization type: {class_reference}")

    if data is None and not strict:
        return None


    # Whatever we have left now is either correct, or invalid
    if isinstance(data, class_reference):
        return data

    raise DeserializeException(
        f"Cannot deserialize '{type(data)}' to '{class_reference}' for '{debug_name}'"
    )


def _deserialize_list(class_reference, list_data, debug_name, throw_on_unhandled, strict):

    if not isinstance(list_data, list):
        raise DeserializeException(f"Cannot deserialize '{type(list_data)}' as a list for {debug_name}")

    if not is_list(class_reference):
        raise DeserializeException(f"Cannot deserialize a list to '{class_reference}' for {debug_name}")

    list_content_type_value = list_content_type(class_reference)

    output = []

    for index, item in enumerate(list_data):
        deserialized = _deserialize(
            list_content_type_value, item, f"{debug_name}[{index}]", throw_on_unhandled, strict
        )
        output.append(deserialized)

    return output



def _deserialize_tuple(class_reference, tuple_data, debug_name, throw_on_unhandled, strict):

    if not isinstance(tuple_data, tuple):
        raise DeserializeException(f"Cannot deserialize '{type(tuple_data)}' as a list for {debug_name}")

    if not is_tuple(class_reference):
        raise DeserializeException(f"Cannot deserialize a tuple to '{class_reference}' for {debug_name}")

    tuple_content_types_value = tuple_content_types(class_reference)

    output = []

    for index, (item, item_type) in enumerate(zip(tuple_data, tuple_content_types_value)):
        deserialized = _deserialize(item_type, item, f"{debug_name}[{index}]", strict)
        output.append(deserialized)

    return tuple(output)


def _deserialize_dict(class_reference, data, debug_name, throw_on_unhandled, strict):
    """Deserialize a dictionary to a Python object."""

    # Check if we are doing a straightforward dictionary parse first, or if it
    # has to be deserialized

    remaining_properties = set(data.keys())

    if not isinstance(data, dict):
        raise DeserializeException(
            f"Data was not dict for instance: {class_reference} for {debug_name}"
        )

    if is_dict(class_reference):
        if class_reference is dict:
            # If types of dictionary entries are not defined, do not deserialize
            return data
        key_type, value_type = dict_content_types(class_reference)
        result = {}

        for dict_key, dict_value in data.items():

            if not isinstance(dict_key, key_type):
                raise DeserializeException(
                    f"Could not deserialize key {dict_key} to type {key_type} for {debug_name}"
                )

            result[dict_key] = _deserialize(
                value_type, dict_value, f"{debug_name}.{dict_key}", throw_on_unhandled, strict
            )

            remaining_properties.remove(dict_key)

        if throw_on_unhandled and len(remaining_properties) > 0:
            raise UnhandledFieldException(
                f"The following field was unhandled: {list(remaining_properties)[0]} for {debug_name}"
            )

        return result

    # It wasn't a straight forward dictionary, so we are in deserialize mode

    hints = typing.get_type_hints(class_reference)

    if len(hints) == 0:
        raise DeserializeException(
            f"Could not deserialize {data} into {class_reference} due to lack of type hints"
        )

    class_instance = class_reference()

    handled_properties = set()

    for attribute_name, attribute_type in hints.items():
        handled_properties.add(attribute_name)

        if _should_ignore(class_reference, attribute_name):
            continue

        property_key = _get_key(class_reference, attribute_name)
        parser_function = _get_parser(class_reference, property_key)
        try:
            value = data[property_key]
            handled_properties.add(property_key)
        except KeyError:
            if not is_union(attribute_type) or type(None) not in union_types(attribute_type):
                raise DeserializeException(f"Unexpected missing value for: {debug_name}")
            value = None

        property_value = parser_function(value)

        deserialized_value = _deserialize(
            attribute_type, property_value, f"{debug_name}.{attribute_name}", throw_on_unhandled, strict
        )
        setattr(class_instance, attribute_name, deserialized_value)

    unhandled = set(data.keys()) - handled_properties
    if len(unhandled) > 0:
        raise UnhandledFieldException(f"Unhandled field: {list(unhandled)[0]}")

    if throw_on_unhandled and len(remaining_properties) > 0:
        raise UnhandledFieldException(UnhandledFieldException(list(remaining_properties)[0]))

    return class_instance
