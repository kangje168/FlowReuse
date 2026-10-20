"""Domain-neutral, deterministic JSON and text building blocks."""
import copy
import json


def input_data(data, params):
    return copy.deepcopy(data)


def pick_field(data, params):
    value = data
    for key in params["path"].split("."):
        if isinstance(value, dict) and key in value:
            value = value[key]
        elif isinstance(value, list) and key.isdigit() and int(key) < len(value):
            value = value[int(key)]
        else:
            raise ValueError(f"Input has no field at path {params['path']}")
    return copy.deepcopy(value)


def format_json(data, params):
    indent = params["indent"]
    if int(indent) != indent:
        raise ValueError("Indentation must be an integer")
    return json.dumps(data, ensure_ascii=False, allow_nan=False, indent=int(indent))


def replace_text(data, params):
    if not isinstance(data, str):
        raise ValueError("Text replacement requires a string; format JSON as text first")
    return data.replace(params["search"], params["replacement"])


def split_text(data, params):
    if not isinstance(data, str):
        raise ValueError("Text splitting requires a string")
    separator = params["separator"].replace("\\n", "\n").replace("\\t", "\t")
    return data.split(separator)


def count_items(data, params):
    if not isinstance(data, (list, dict, str)):
        raise ValueError("Counting requires an array, object or string")
    return {"count": len(data), "kind": "array" if isinstance(data, list) else "object" if isinstance(data, dict) else "text"}


DEFINITIONS = {
    "input_data": {"name":"Workflow input", "description":"Accept any JSON value: text, object, array or number", "input":None, "output":"json", "defaults":{}, "fields":[], "function":input_data, "color":"blue", "symbol":"↳", "category":"general"},
    "pick_field": {"name":"Extract field", "description":"Read an object field or array entry, such as items.0.name", "input":"json", "output":"json", "defaults":{"path":"items"}, "fields":[{"key":"path","label":"Field path","type":"text"}], "function":pick_field, "color":"violet", "symbol":"⌘", "category":"general"},
    "format_json": {"name":"JSON to text", "description":"Format a JSON value as reusable text", "input":"json", "output":"text", "defaults":{"indent":2}, "fields":[{"key":"indent","label":"Indentation spaces","type":"number","min":0,"max":8}], "function":format_json, "color":"green", "symbol":"{ }", "category":"general"},
    "replace_text": {"name":"Replace text", "description":"Replace text using a fixed rule, without a model", "input":"text", "output":"text", "defaults":{"search":"old text","replacement":"new text"}, "fields":[{"key":"search","label":"Find text","type":"text"},{"key":"replacement","label":"Replacement (may be empty)","type":"text","allow_empty":True}], "function":replace_text, "color":"violet", "symbol":"Aa", "category":"general"},
    "split_text": {"name":"Split text", "description":"Split text using a delimiter into a JSON array", "input":"text", "output":"json", "defaults":{"separator":"\\n"}, "fields":[{"key":"separator","label":"Delimiter (\\n means newline)","type":"text"}], "function":split_text, "color":"amber", "symbol":"⋮", "category":"general"},
    "count_items": {"name":"Count", "description":"Count array entries, object fields or text characters", "input":"json", "output":"json", "defaults":{}, "fields":[], "function":count_items, "color":"green", "symbol":"#", "category":"general"},
}
