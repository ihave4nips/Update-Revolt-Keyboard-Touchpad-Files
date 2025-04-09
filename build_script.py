#!/usr/bin/env python3
import subprocess
import re
import os
import sys
import time
import tkinter as tk

def open_keyboard_file():
    filepath = "Keyboard_without_number_pad.txt"
    print(f"=== Opening {filepath} in Kate ===")

    if not os.path.exists(filepath):
        print(f"Error: {filepath} not found.")
        sys.exit(1)

    try:
        subprocess.Popen(["kate", filepath])
    except FileNotFoundError:
        print("Kate is not installed or not in PATH.")
        sys.exit(1)

    def on_done():
        root.destroy()

    root = tk.Tk()
    root.title("Continue")
    root.geometry("300x100")
    tk.Label(root, text="Click when you're done editing the file.").pack(pady=10)
    tk.Button(root, text="I'm Done", command=on_done).pack()
    root.mainloop()

def run_matrix_decoder():
    print("=== Running matrix_decoder.ino ===")
    fqbn = "teensy:avr:teensy41:usb=keyboard"
    port = "usb3/3-7"

    try:
        subprocess.run(["arduino-cli", "compile", "--fqbn", fqbn, "matrix_decoder"], check=True)
        subprocess.run(["arduino-cli", "upload", "-p", port, "--fqbn", fqbn, "matrix_decoder"], check=True)
        print("Upload successful! Waiting briefly before opening the file...")
        time.sleep(2)
        open_keyboard_file()
    except subprocess.CalledProcessError as e:
        print("Error running matrix_decoder.ino:")
        print(e.stderr)
        sys.exit(1)

def run_matrix_generator():
    print("=== Running matrixgenerator.py with automated inputs ===")
    input_data = "1\n4\nn\n"
    try:
        result = subprocess.run(["python", "matrixgenerator.py"], input=input_data, capture_output=True, text=True, check=True)
        print(result.stdout)
        return result.stdout
    except subprocess.CalledProcessError as e:
        print("Error running matrixgenerator.py:")
        print(e.stderr)
        sys.exit(1)

def extract_matrices(output):
    matrices = {}
    pattern = re.compile(r"-{5,}\s*(\w+)\s*-{5,}\s*\n(\{(?:[^{}]|\{[^{}]*\})*\})", re.DOTALL)
    matches = pattern.findall(output)
    for header, block in matches:
        matrices[header.strip()] = block.strip()

    pin_info = {"input_pins": [], "output_pins": []}

    # Extract the TEENSY PINS block specifically
    teensy_input_match = re.search(r"TEENSY PINS.*?input pins:\s*\[([^\]]+)\]", output, re.DOTALL)
    teensy_output_match = re.search(r"TEENSY PINS.*?output pins:\s*\[([^\]]+)\]", output, re.DOTALL)

    if teensy_input_match:
        pin_info["input_pins"] = [int(x.strip()) for x in teensy_input_match.group(1).split(',')]
    if teensy_output_match:
        pin_info["output_pins"] = [int(x.strip()) for x in teensy_output_match.group(1).split(',')]

    return matrices, pin_info


def update_script3revolt(matrices, pins):
    filename = os.path.join("script3revolt", "script3revolt.ino")
    if not os.path.exists(filename):
        print(f"{filename} not found!")
        sys.exit(1)

    with open(filename, "r") as f:
        content = f.read()

    def replace_matrix(name, new_matrix, content):
        pattern = re.compile(rf"int {name.lower()}\[rows_max\]\[cols_max\] = \{{.*?\n\}};", re.DOTALL)
        new_block = f"int {name.lower()}[rows_max][cols_max] = {new_matrix};"
        if pattern.search(content):
            return pattern.sub(new_block, content)
        else:
            alt_pattern = re.compile(rf"int {name.lower()}\[rows_max\]\[cols_max\] = \{{\n\s*//.*?\n\}};", re.DOTALL)
            return alt_pattern.sub(new_block, content)

    def replace_old_key(new_matrix):
        pattern = re.compile(r"boolean old_key\[rows_max\]\[cols_max\] = \{.*?\};", re.DOTALL)
        return pattern.sub(f"boolean old_key[rows_max][cols_max] = {new_matrix};", content)

    def replace_pin_array(name, pins_list):
        pin_string = "{" + ",".join(map(str, pins_list)) + "}"
        # Match line like: int Row_IO[rows_max] = {}; // comment
        pattern = re.compile(rf"(int {name}\[.*?\] = )\{{.*?\}}(;[ \t]*//.*)")
        return pattern.sub(rf"\1{pin_string}\2", content)


    def replace_size(name, value):
        pattern = re.compile(rf"const byte {name} = .*?;")
        return pattern.sub(f"const byte {name} = {value};", content)

    rows_max = len(matrices["ONE"].strip().split("\n")) - 2
    cols_max = len(matrices["ONE"].split("\n")[1].strip().strip("{} ").split(","))


    print("Updating script3revolt.ino with the following extracted values:")
    print(f"  Row_IO (output pins):  {pins['output_pins']}")
    print(f"  Col_IO (input pins): {pins['input_pins']}")



    content = replace_size("rows_max", rows_max)
    content = replace_size("cols_max", cols_max)
    content = replace_matrix("normal", matrices["KEY"], content)
    content = replace_matrix("modifier", matrices["MODIFIER"], content)
    content = replace_matrix("media", matrices["FN"], content)
    content = replace_old_key(matrices["ONE"])
    content = replace_pin_array("Row_IO", pins["output_pins"])
    content = replace_pin_array("Col_IO", pins["input_pins"])

    with open(filename, "w") as f:
        f.write(content)
    print(f"{filename} has been updated with new matrices and pin mappings.")


def upload_script3revolt():
    print("=== Compiling and uploading script3revolt.ino ===")
    fqbn = "teensy:avr:teensy41:usb=keyboard"
    port = "usb3/3-7"
    sketch_folder = "script3revolt"

    try:
        subprocess.run(["arduino-cli", "compile", "--fqbn", fqbn, sketch_folder], check=True)
        subprocess.run(["arduino-cli", "upload", "-p", port, "--fqbn", fqbn, sketch_folder], check=True)
        print("script3revolt.ino uploaded successfully!")
    except subprocess.CalledProcessError as e:
        print("Error uploading script3revolt.ino:")
        print(e.stderr)
        sys.exit(1)

def main():
    run_matrix_decoder()

    txt_file = "Keyboard_without_number_pad.txt"
    if not os.path.exists(txt_file):
        print(f"Error: {txt_file} not found!")
        sys.exit(1)
    print(f"Found {txt_file}.")

    generator_output = run_matrix_generator()
    matrices, pins = extract_matrices(generator_output)

    if matrices:
        print("Extracted matrices:")
        for k, v in matrices.items():
            print(f"--- {k} matrix ---\n{v}\n")
    else:
        print("No matrices were extracted; aborting update to script3revolt.ino.")
        sys.exit(1)

    update_script3revolt(matrices, pins)
    upload_script3revolt()
if __name__ == "__main__":
    main()
