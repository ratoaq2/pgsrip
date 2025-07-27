import os
import typing

import yaml


def read_yaml(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def from_yaml(test_filename: str, test_name: typing.Optional[str] = None):
    base_path = os.path.splitext(test_filename)[0]
    yml_file = f'{base_path}__{test_name}.yml' if test_name else f'{base_path}.yml'

    return read_yaml(yml_file)
