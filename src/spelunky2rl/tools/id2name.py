import re
import os

pattern = re.compile(r'-\s*(\d+)\s+([A-Z0-9_]+)\s*=\s*(.*)')
subtype_pattern = re.compile(r'\[([^\]]+)\]')

entities_dict = {}

file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "entities-hierarchy.md")

with open(file_path, 'r', encoding='utf-8') as f:
    for line in f:
        line = line.strip()
        if not line.startswith('-'):
            continue

        match = pattern.match(line)
        if match:
            entity_id_str, name, chain_str = match.groups()
            entity_id = int(entity_id_str)  # convert to int
            subtypes = subtype_pattern.findall(chain_str)

            entities_dict[entity_id] = {
                'name': name,
                'subtypes': subtypes
            }


def id2name(entity_id: int):
    """Return the name and subtypes for the given entity_id (as integer)."""
    return entities_dict.get(entity_id, None)

if __name__ == "__main__":
    test_id = '001'
    result = id2name(test_id)
    if result:
        print(f"Entity ID: {test_id}, Name: {result['name']}, Subtypes: {result['subtypes']}")
    else:
        print(f"No data found for Entity ID: {test_id}")