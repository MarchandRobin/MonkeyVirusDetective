import exiftool
import re
import hashlib
import requests
import json
from tabulate import tabulate
import magic
import sys
import os
import subprocess
import re

headers = {
    "accept": "application/json",
    "x-apikey": "bb18a62f2101e29a40880b6b92e39bdddb97e55c3240a056139e18d291a91d1d"
}

try :
    file_path = sys.argv[1]
except IndexError:
    print("Please specify a file path")
    sys.exit(1)



OS = re.compile(r"Windows|Linux|MacOS", re.IGNORECASE)
Linux_Distribution = re.compile(r"(?i)(?:\b|(?<=\s))(Ubuntu|Debian|CentOS|Fedora|RedHat|ArchLinux|Kali|Parrot|Alpine|Gentoo|OpenSUSE|Slackware|Manjaro|LinuxMint|Zorin|Elementary|Solus|FreeBSD|OpenBSD|NetBSD|DragonFlyBSD|TrueOS|GhostBSD|HardenedBSD|MidnightBSD|macOS|iOS|watchOS|tvOS|iPadOS|Android|ChromeOS)(?=\s|\b)")
Ubuntu_Version = re.compile(r"Ubuntu (\d+\.\d+\.\d+)", re.IGNORECASE)
File = re.compile(r"\.c(?!\w)|\.cpp(?!\w)|\.exe(?!\w)", re.IGNORECASE)


def list_functions_in_binary(file_path):
    try:
        output = subprocess.check_output(["gdb", "-batch", "-ex", "python import sys; sys.path.insert(0, '')", "-ex", "python import gdb; gdb.execute('file " + file_path + "')", "-ex", "python import gdb; print(gdb.execute('info functions', to_string=True))"], stderr=subprocess.STDOUT)
        functions_output = output.decode("utf-8")
        functions_list = functions_output.splitlines()[1:]  # Skip the first line (header)
        return functions_list
    except subprocess.CalledProcessError:
        return []


def is_binary(file_path):
    try:
        with open(file_path, "rb") as file:
            content = file.read()
    except OSError:
        return True

    if any(pattern in content for pattern in [b"\x7fELF", b"MZ", b"PE\x00\x00", b"\x00\x61\x73\x6D"]):
        return True

    if file_path.endswith((".exe", ".dll")):
        return True

    try:
        file_type = magic.from_file(file_path)
    except OSError:
        return True
    if any(type_check in file_type for type_check in ["ELF", "PE32"]):
        return True

    if b"\xef\xbf\xbd" in content:
        return True

    return False



def get_metadata(file_path):
    with exiftool.ExifTool() as et:
        metadata = et.get_metadata_batch([file_path])

    if metadata:
        try:
            metadata_table = [["File Size", "File Name", "File Type", "File Modify Date"]]
            for data in metadata:
                file_size = data.get("File:FileSize")
                file_name = data.get("File:FileName")
                file_type = data.get("File:FileType")
                file_modify_date = data.get("File:FileModifyDate")
                metadata_table.append([file_size, file_name, file_type, file_modify_date])
            return metadata_table
        except KeyError:
            return "No metadata found"
    else:
        return "No metadata found"


def get_decoded_content(file_path):
    with open(file_path, "rb") as file:
        content = file.read()
        encodings = ["utf-8", "latin-1", "ascii"]  # Add more encodings if necessary
        decoded_content = None
        for encoding in encodings:
            try:
                decoded_content = content.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        if decoded_content is None:
            raise ValueError(f"Could not decode file {file_path} with any of the encodings {encodings}.")
        return decoded_content


def get_additional_info(decoded_content):
    additional_info_table = [["OS", ", ".join(set(OS.findall(decoded_content)))],
                             ["Linux Distribution", ", ".join(set(Linux_Distribution.findall(decoded_content)))],
                             ["Ubuntu Version", ", ".join(set(Ubuntu_Version.findall(decoded_content)) or ["Not Found"])],
                             ["File", ", ".join(set(File.findall(decoded_content)))],
                             ["isStriped", "True" if "strip" in subprocess.check_output(["file", file_path]).decode("utf-8") else "False"]]
    return additional_info_table


def get_virus_total_results(content):
    content_encoded = content.encode("utf-8")  # Encode the content as UTF-8 bytes
    hash_md5 = hashlib.md5(content_encoded).hexdigest()
    url = "https://www.virustotal.com/api/v3/files/" + hash_md5

    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        json_response = response.json()
        data = json_response.get("data")
        attributes = data.get("attributes")
        last_analysis_stats = attributes.get("last_analysis_stats")
        last_analysis_results = attributes.get("last_analysis_results")
        last_analysis_results_table = []
        for key, value in last_analysis_results.items():
            last_analysis_results_table.append([key, value.get("category"), value.get("result")])

        virus_total_results = {
            "virus_total_results": last_analysis_results_table,
            "virus_total_stats": {
                "Harmless": last_analysis_stats.get("harmless"),
                "Malicious": last_analysis_stats.get("malicious"),
                "Suspicious": last_analysis_stats.get("suspicious"),
                "Timeout": last_analysis_stats.get("timeout"),
                "Undetected": last_analysis_stats.get("undetected"),
                "Type Unsupported": last_analysis_stats.get("type-unsupported"),
                "Failure": last_analysis_stats.get("failure")
            }
        }
        return virus_total_results
    elif response.status_code == 404:
        return "Unknown file"
    else:
        return "Error: " + str(response.status_code)

def generate_json_output(metadata, additional_info, virus_total_results):
    result = {
        "metadata": metadata,
        "additional_info": additional_info,
        "virus_total_results": virus_total_results
    }
    result_json = json.dumps(result, indent=4)
    return result_json

def summarize_binary_behavior(file_path):
    import subprocess
    def check_file_access(file_path):
        try:
            output = subprocess.check_output(["strace", "-e", "file", file_path], stderr=subprocess.STDOUT)
            output = output.decode("utf-8")

            # Search for file-related system calls in the strace output
            file_access_regex = re.compile(r"openat\(AT_FDCWD, \".*\", .*")
            file_access_regex2 = re.compile(r"access\(.*\)")
            file_accesses = file_access_regex.findall(output)
            file_accesses2 = file_access_regex2.findall(output)
            file_accesses.extend(file_accesses2)
            return file_accesses
        except subprocess.CalledProcessError:
            return "Error"

    def check_subprocess_creation(file_path):
        try:
            output = subprocess.check_output(["strace", "-f", "-e", "execve", "-s", "10000", file_path], stderr=subprocess.STDOUT)
            output = output.decode("utf-8")

            # Search for subprocess creations in the strace output
            subprocess_regex = re.compile(r"execve\((.*?)\)")
            subprocesses = subprocess_regex.findall(output)
            return subprocesses
        except subprocess.CalledProcessError:
            return "Error"

    # Get file accesses and subprocess creations
    file_accesses = check_file_access(file_path)
    subprocesses = check_subprocess_creation(file_path)

    # Prepare the summarized overview
    summary = f"Binary Summary: {file_path}\n"
    summary += "=" * 50 + "\n"

    if file_accesses != "Error":
        summary += "File Accesses:\n"
        if file_accesses:
            for access in file_accesses:
                summary += f"  - {access}\n"
        else:
            summary += "No file accesses found.\n"
        summary += "\n"

    if subprocesses != "Error":
        summary += "Subprocess Creations:\n"
        if subprocesses:
            for subprocess in subprocesses:
                summary += f"  - {subprocess}\n"
        else:
            summary += "No subprocess creations found.\n"
        summary += "\n"

    output = summary
    return output



if is_binary(file_path):
    metadata = get_metadata(file_path)
    decoded_content = get_decoded_content(file_path)
    additional_info = get_additional_info(decoded_content)
    virus_total_results = get_virus_total_results(decoded_content)
    json_output = generate_json_output(metadata, additional_info, virus_total_results)


    print(json_output)
    file_accesses = summarize_binary_behavior(file_path)
    print(f"File accesses: {file_accesses}")
    functions = list_functions_in_binary(file_path)
    print(f"Found {(len(functions)-1)/2} functions in the binary:")
    for function in functions:
        print(function)

else:
    print("File is not binary")
