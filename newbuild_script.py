#!/usr/bin/env python3
import subprocess
import re
import os
import sys
import time
import tkinter as tk
from tkinter import ttk

def open_keyboard_file():
    filepath = "Keyboard_without_number_pad.txt"
    total  = 60   # seconds to wait
    LINE   = 1   # change to the line you want
    COL    = 33   # change to the column you want

    print(f"=== Opening {filepath} in Kate at Ln {LINE}, Col {COL} for {total} s ===")

    if not os.path.exists(filepath):
        print(f"Error: {filepath} not found.")
        sys.exit(1)

    # launch Kate with cursor placement
    try:
        kate_proc = subprocess.Popen([
            "kate",
            "--line",   str(LINE),
            "--column", str(COL),
            filepath
        ])
    except FileNotFoundError:
        print("Kate is not installed or not in PATH.")
        sys.exit(1)

    # build countdown window
    timer = tk.Tk()
    timer.title("Time Remaining")
    timer.geometry("300x140")
    timer.resizable(False, False)

    # show cursor position
    pos_label = tk.Label(
        timer,
        text=f"Cursor at Ln {LINE}, Col {COL}",
        font=("Arial", 12)
    )
    pos_label.pack(pady=(15, 5))

    # countdown label
    time_label = tk.Label(
        timer,
        text=f"{total} s remaining",
        font=("Arial", 14, "bold")
    )
    time_label.pack()

    # progress bar
    progress = ttk.Progressbar(timer, maximum=total, length=260)
    progress.pack(pady=(5, 15))
    progress["value"] = total

    def countdown(remaining):
        if remaining >= 0:
            time_label.config(text=f"{remaining} s remaining")
            progress["value"] = remaining
            timer.after(1000, countdown, remaining - 1)
        else:
            timer.destroy()

    countdown(total)
    timer.mainloop()

    # time's up → close Kate
    print("=== Time's up: closing Kate ===")
    kate_proc.terminate()
    try:
        kate_proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        kate_proc.kill()
        kate_proc.wait()

    print("=== Kate closed, proceeding with script ===")

def run_matrix_decoder():
    print("=== Running matrix_decoder.ino ===")
    fqbn = "teensy:avr:teensy41:usb=hid"
    port = "usb3/3-7"

    try:
        subprocess.run(
            ["arduino-cli", "compile", "--fqbn", fqbn, "matrix_decoder"],
            check=True
        )
        subprocess.run(
            ["arduino-cli", "upload", "-p", port, "--fqbn", fqbn, "matrix_decoder"],
            check=True
        )
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
        result = subprocess.run(
            ["python3", "matrixgenerator.py"],
            input=input_data,
            capture_output=True,
            text=True,
            check=True
        )
        print(result.stdout)
        return result.stdout
    except subprocess.CalledProcessError as e:
        print("Error running matrixgenerator.py:")
        print(e.stderr)
        sys.exit(1)

def extract_matrices(output):
    matrices = {}
    pattern = re.compile(
        r"-{5,}\s*(\w+)\s*-{5,}\s*\n(\{(?:[^{}]|\{[^{}]*\})*\})",
        re.DOTALL
    )
    for header, block in pattern.findall(output):
        matrices[header.strip()] = block.strip()

    pin_info = {"input_pins": [], "output_pins": []}
    in_match = re.search(
        r"TEENSY PINS.*?input pins:\s*\[([^\]]+)\]",
        output, re.DOTALL
    )
    out_match = re.search(
        r"TEENSY PINS.*?output pins:\s*\[([^\]]+)\]",
        output, re.DOTALL
    )
    if in_match:
        pin_info["input_pins"] = [int(x.strip()) for x in in_match.group(1).split(',')]
    if out_match:
        pin_info["output_pins"] = [int(x.strip()) for x in out_match.group(1).split(',')]

    return matrices, pin_info

def update_script3revolt(matrices, pins):
    filename = os.path.join("script3revolt", "script3revolt.ino")
    if not os.path.exists(filename):
        print(f"{filename} not found!")
        sys.exit(1)

    content = open(filename).read()

    def replace_size(name, value, txt):
        return re.sub(
            rf"const byte {name} = .*?;",
            f"const byte {name} = {value};",
            txt
        )

    def replace_matrix(name, new_matrix, txt):
        # replace int <name>[rows_max][cols_max] blocks
        pat = re.compile(
            rf"int {name}\[rows_max\]\[cols_max\] = \{{.*?\}};",
            re.DOTALL
        )
        return pat.sub(f"int {name}[rows_max][cols_max] = {new_matrix};", txt)

    def replace_old_key(new_matrix, txt):
        pat = re.compile(
            r"boolean old_key\[rows_max\]\[cols_max\] = \{.*?\};",
            re.DOTALL
        )
        return pat.sub(f"boolean old_key[rows_max][cols_max] = {new_matrix};", txt)

    def replace_pin_array(name, pins_list, txt):
        pin_str = "{" + ",".join(map(str, pins_list)) + "}"
        pat = re.compile(rf"(int {name}\[.*?\] = )\{{.*?\}}(;[ \t]*//.*)")
        return pat.sub(rf"\1{pin_str}\2", txt)

    # derive sizes
    rows_max = len(matrices["ONE"].strip().splitlines()) - 2
    cols_max = len(matrices["ONE"].splitlines()[1].strip().strip("{} ").split(","))

    print("Updating script3revolt.ino with:")
    print(f"  rows_max = {rows_max}, cols_max = {cols_max}")
    print(f"  Row_IO = {pins['output_pins']}")
    print(f"  Col_IO = {pins['input_pins']}")

    content = replace_size("rows_max", rows_max, content)
    content = replace_size("cols_max", cols_max, content)
    content = replace_matrix("normal", matrices["KEY"], content)
    content = replace_matrix("modifier", matrices["MODIFIER"], content)
    content = replace_matrix("media", matrices["FN"], content)
    content = replace_old_key(matrices["ONE"], content)
    content = replace_pin_array("Row_IO", pins["output_pins"], content)
    content = replace_pin_array("Col_IO", pins["input_pins"], content)

    with open(filename, "w") as f:
        f.write(content)
    print(f"{filename} updated successfully.")

def upload_script3revolt():
    print("=== Compiling and uploading script3revolt.ino ===")
    fqbn = "teensy:avr:teensy41:usb=hid"
    port = "usb3/3-7"
    folder = "script3revolt"
    try:
        subprocess.run(
            ["arduino-cli", "compile", "--fqbn", fqbn, folder],
            check=True
        )
        subprocess.run(
            ["arduino-cli", "upload", "-p", port, "--fqbn", fqbn, folder],
            check=True
        )
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

    generator_output = run_matrix_generator()
    matrices, pins = extract_matrices(generator_output)

    if not matrices:
        print("No matrices extracted; aborting.")
        sys.exit(1)

    update_script3revolt(matrices, pins)
    upload_script3revolt()


if __name__ == "__main__":
    main()
