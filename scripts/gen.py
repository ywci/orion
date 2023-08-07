import re
import os
import sys
import json
import time
import requests
import argparse
import html2text
from bs4 import BeautifulSoup

TEMPERATURE = 0
MAX_TOKENS = 0
API_KEY = ""
TARGET = ""
MODEL = ""
URL = ""

INFO = True
WARN = True

PATH_BUILD = "build"
WAITTIME = 2 # sec
RETRY_MAX = 5

STEPS = ["decompose", 
         "encapsulate", 
         "top",
         "test"]

ANNOTATION = {"begin" : "####[BEGIN]####",
              "end"   : "####[END]####",
              "no_impl": "####[NO IMPLEMENTATION]####"}

HOME = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def show_log(content, tag):
    soup = BeautifulSoup(content, 'html.parser')
    if isinstance(soup, BeautifulSoup):
        html = soup.get_text()
        text = html2text.html2text(html)
        print("[%s]\n%s" % (tag, text))
    else:
        print("[%s] %s" % (tag, str(content)))

def show_err(content):
    show_log(content, "Error")
    sys.exit()

def show_warn(content):
    if WARN:
        show_log(content, "WARNING")

def show_info(info):
    if INFO:
        print("[Info] %s" % info)

def show_content(content):
    if INFO:
        print("***************")
        print("*     GPT     *")
        print("***************")
        print(content)

def is_well_formed_module(code):
    stack = []
    for char in code:
        if char in "{[(":
            stack.append(char)
        elif char in "}])":
            if len(stack) == 0:
                return False
            opening = stack.pop()
            if (opening == "{" and char != "}") or \
               (opening == "[" and char != "]") or \
               (opening == "(" and char != ")"):
                return False
    return len(stack) == 0

def is_well_formed_interface(module, interface):
    line = interface[0].strip()
    if type(interface) == list and len(interface) > 0 and line.startswith("- "):
        pattern = r"- (\w+): (\w+)\(([\w()]+)\)"
        match = re.fullmatch(pattern, line)
        if match:
            show_warn("The description of interface for %s is too brief" % module)
        else:
            return True
    return False

def dict_to_markdown(dct, indent=0):
    md_lines = []
    for k, v in dct.items():
        if isinstance(v, dict):
            md_lines.append(f"{'  ' * indent}- {k}\n")
            md_lines.extend(dict_to_markdown(v, indent + 1))
        else:
            md_lines.append(f"{'  ' * indent}- {k}: {v}\n")
    return md_lines

def parse_to_dict(name, text):
    try:
        return json.loads(text)
    except:
        show_warn("failed to parse %s" % name)

def remove_files(dirname):
    if not os.path.exists(dirname):
        return
    for filename in os.listdir(dirname):
        file_path = os.path.join(dirname, filename)
        try:
            if os.path.isfile(file_path):
                os.unlink(file_path)
        except:
            show_err('cannot delete %s' % filename)

def get_completion(content):
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer " + API_KEY
    }
    data = {
        "messages": [{'role': 'user', 'content': content}],
        "temperature": TEMPERATURE
    }
    if MODEL:
        data.update({"model": MODEL})
    if MAX_TOKENS > 0:
        data.update({"max_tokens": MAX_TOKENS})
    try:
        response = requests.post(URL, headers=headers, data=json.dumps(data))
        if response.status_code == 200:
            return json.loads(response.content.decode("utf-8"))
        else:
            show_warn(response.text)
    except:
        show_warn("faile to request")

def get_content(completion):
    choices = completion.get("choices")
    if choices:
        return choices[0]["message"]["content"]

def decompose(name):
    return "\nPlease provide all main modules of %s using JSON (do not explicitely declare 'modules' or 'submodules'), organized in a hierarchical structure and without including any registers, signals and comments.\n" % name

# Please note that the generated module does not include any detailed implementation of sub-modules. 
def encapsulate(name, parent):
    intf = ""
    if name in parent:
        show_info("Sub-modules of %s: %s" % (name, " ".join(list(parent[name].keys()))))
        for i in parent[name]:
            if not parent[name][i]['interface']:
                show_err("failed to generate %s (cannot get the interface of %s)" % (name, i))
            intf = intf + ''.join(parent[name][i]['interface']) + '\n'
        show_info("%s" % intf)
    return  "".join([intf, "\nPlease provide comments on the interface of %s using unordered list of markdown language. \
            These comments should specify the bit-width of each interface signal and must be enclosed within %s and %s. \
            After that, please provide a high-level implementation of the module %s in %s (if the given implementation is incomplete, pleate comment with %s). \
            The %s code of %s must be enclosed within %s and %s. \n" % (name, ANNOTATION['begin'], ANNOTATION['end'], name, TARGET, ANNOTATION['no_impl'], TARGET, name, ANNOTATION['begin'], ANNOTATION['end'])])

def set_target(name):
    return "Create %s in %s:\n" % (name, TARGET)

def check_module(name, module, content):
    buf = []
    body = None
    iface = True
    begin = False
    interface = None
    lines = content.split('\n')
    for i in range(len(lines)):
        l = lines[i]
        if l.startswith(ANNOTATION["begin"]):
            begin = True
            continue
        elif l.startswith(ANNOTATION["end"]):
            if not iface:
                complete = True
                text = "".join(buf)
                if TARGET == "chisel":
                    if "class" not in text:
                        complete = False
                if complete:
                    if is_well_formed_module(text):
                        body = list(map(lambda line: line + '\n', text.strip().split('\n')))
                    else:
                        show_warn("the module %s in %s is not well-formed" % (module, name))
                else:
                    show_warn("incomplete implementation of %s in %s" % (module, name))
                break
            else:
                text = re.sub(r"`([^`]+)`", r"\1: ", "".join(buf))
                interface = list(map(lambda line: line + '\n', text.strip().split('\n')))
                if is_well_formed_interface(module, interface):
                    interface.insert(0, "The interface of %s should contain %d signals, as follows:\n" % (module, len(interface)))
                    begin = False
                    iface = False
                    buf = []
                    continue
                else:
                    show_warn("the interface of %s in %s is not well-formed" % (module, name))
                    interface = None
                    break
        elif (iface and (module in l or not l)) or l.startswith("```") or l.lower().startswith(TARGET.lower()) or not begin:
            continue
        pattern = r"//\s+(\w+)\s+implementation\s+here"
        if ("..." in l) or ("logic here" in l) or ("goes here" in l) or ("TODO" in l) or (ANNOTATION['no_impl'] in l) or re.fullmatch(pattern, l):
            show_warn("incomplete implementation of %s in %s" % (module, name))
            break
        buf.append(l + '\n')
    if interface and body:
        return (interface, body)
    else:
        return (None, None)

def gen_module(name, module, body):
    assert(type(body) == list)
    dirname = os.path.join(HOME, PATH_BUILD, TARGET, "src", "main", name)
    if not os.path.exists(dirname):
        os.makedirs(dirname)
    filename = os.path.join(dirname, module)
    if TARGET == 'chisel':
        filename = "%s.scala" % filename
    with open(filename, 'w') as f:
        f.writelines(body)

def gen_doc(name, text):
    try:
        assert(type(text) == list)
        path = os.path.join(HOME, "doc", "%s.md" % name)
        with open(path, 'w') as f:
            f.writelines(''.join(text))
    except:
        show_err("failed to generate doc for %s" % str(name))

def initialize(name, modules):
    try:
        path = os.path.join(HOME, PATH_BUILD, TARGET, "src", "main", name)
        remove_files(path)
        path = os.path.join(HOME, "doc")
        remove_files(path)
        lines = dict_to_markdown(modules)
        gen_doc(name, lines)
    except:
        show_err("failed to initialize %s" % str(name))

def create(file_name):
    name = file_name.split('.')[0]
    path = os.path.join(HOME, "prompts", file_name)
    with open(path, 'r') as file:
        prompt = file.read()
    queue = None
    module = None
    modules = None
    requirement = None
    has_target = False
    retry_times = 0
    parent = {}
    child = {}
    for step in STEPS:
        while True:
            if step == "decompose":
                requirement = decompose(name)
            elif step == "encapsulate":
                has_target = True
                if not module:
                    head = queue.pop(0)
                    assert(type(head) == dict)
                    module = list(head.keys())[0]
                    children = head[module]
                    if children:
                        parent.update({module: {key: {} for key in list(children.keys())}})
                        child.update({key: {"parent": module} for key in list(children.keys())})
                        queue.insert(0, {module: {}})
                        queue.insert(0, children)
                        module = None
                        continue
                    elif len(head) > 1:
                        del head[module]
                        queue.insert(0, head)
                show_info("Generate %s of %s ..." % (module, name))
                requirement = encapsulate(module, parent)
                if WAITTIME > 0:
                    time.sleep(WAITTIME)
            elif step == "top":
                pass
            if requirement:
                header = ''
                if has_target:
                    header = set_target(name)
                completion = get_completion(header + prompt + '\n' + requirement)
                if not completion:
                    retry_times = retry_times + 1
                    if retry_times == RETRY_MAX:
                        show_err("failed to generate %s" % name)
                    continue
                content = get_content(completion)
                show_content(content)
            else:
                content = None
            if step == "decompose":
                modules = parse_to_dict(name, content)
                if modules:
                    initialize(name, modules)
                    queue = list(map(lambda m: {m: modules[name][m]}, modules[name].keys()))
                    parent.update({name: {key: {} for key in list(modules[name].keys())}})
                    child.update({key: {"parent": name} for key in list(modules[name].keys())})
                    requirement = None
                    retry_times = 0
                    break
                else:
                    retry_times = retry_times + 1
                    if retry_times == RETRY_MAX:
                        show_err("failed to decompose %s" % name)
            elif step == "encapsulate":
                assert(module and module in child and child[module]['parent'] in parent and module in parent[child[module]['parent']])
                if content:
                    interface, body = check_module(name, module, content)
                    if body:
                        assert(interface)
                        parent[child[module]['parent']][module].update({'interface': interface})
                        gen_doc(module, interface)
                        gen_module(name, module, body)
                        retry_times = 0
                        module = None
                    else:
                        retry_times = retry_times + 1
                        if retry_times == RETRY_MAX:
                            show_err("failed to generate %s in %s" % (module, name))
                        continue
                else:
                    module = None
                if not queue:
                    has_target = False
                    requirement = None
                    break
            else:
                break

def generate():
    path = os.path.join(HOME, "prompts")
    for file_name in os.listdir(path):
        create(file_name)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='OpenAI API client.')
    parser.add_argument('model', type=str, help='Model name')
    parser.add_argument('api_key', type=str, help='OpenAI API key')
    parser.add_argument('url', type=str, help='OpenAI full URL')
    parser.add_argument('temperature', type=str, help='A scaling factor')
    parser.add_argument('max_tokens', type=int, help='Maximum tokens')
    parser.add_argument('target', type=str, help='Target language')
    args = parser.parse_args(sys.argv[1:])
    model = args.model if args.model != 'default' else ''
    api_key = args.api_key
    url = args.url
    temperature = args.temperature
    max_tokens = args.max_tokens
    target = args.target
    if not api_key or not url or not temperature or not target:
        raise Exception('invalid configuration')
    TEMPERATURE = float(temperature)
    MAX_TOKENS = int(max_tokens)
    URL = url
    API_KEY = api_key
    TARGET = target
    MODEL = model
    generate()
