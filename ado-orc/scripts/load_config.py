import os
import yaml

def load_modules(config_path):
    """
    Loads modules from config/config.yml and returns a dictionary {name: path}
    """
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    modules_list = config.get('folders') or config.get('modules')
    modules_dict = {}
    for entry in modules_list:
        name = entry['name']
        path = entry['path'].rstrip('/') + '/'
        modules_dict[name] = path
    return modules_dict

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python load_config.py <config_path>")
        sys.exit(1)
    config_path = sys.argv[1]
    modules = load_modules(config_path)
    print(modules)
