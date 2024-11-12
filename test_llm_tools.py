#!/usr/bin/env python3
import requests
import json
import argparse
import sys
import os
from typing import List, Dict
from pathlib import Path
from typing import List, Dict
from datetime import datetime

def create_filesystem_tool():
    return {
        "name": "list_directory",
        "description": "List all files in a directory, optionally filtering by file extension",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The directory path to search in. Special values: 'current' for current directory, '..' for parent directory, 'D:' for drive root"
                },
                "extension": {
                    "type": "string",
                    "description": "Optional file extension to filter by (e.g., '.txt', '.py', '.js')"
                },
                "recursive": {
                    "type": "boolean",
                    "description": "Whether to search subdirectories",
                    "default": False
                }
            },
            "required": ["path"]
        }
    }

def create_file_reader_tool():
    return {
        "name": "read_files",
        "description": "Read a batch of one or more files and return their text, each preceded by a delimiter",
        "parameters": {
            "type": "object",
            "properties": {
                "file_paths": {
                    "type": "array",
                    "items": {
                        "type": "string"
                    },
                    "description": "A list of file paths to read"
                }
            },
            "required": ["file_paths"]
        }
    }

def normalize_extension(extension: str) -> str:
    """Normalize file extension to include the dot and lowercase"""
    if not extension:
        return ""
    ext = extension.lower()
    return f".{ext.lstrip('.')}"

def normalize_path(path_str: str) -> Path:
    """Safely normalize and resolve various path formats"""
    try:
        # Handle special cases
        if path_str.lower() in ['current', '.']:
            return Path.cwd()
        elif path_str == '..':
            return Path.cwd().parent
        elif path_str.lower().endswith(':'):  # Handle drive root like 'D:'
            # Add backslash to ensure root directory
            return Path(f"{path_str}\\").resolve()
        elif path_str.lower().endswith(':\\'):  # Handle drive root like 'D:\'
            return Path(path_str).resolve()
        elif path_str.lower() in ['current', '.', '']:
            return Path.cwd()
        else:
            # Handle relative paths
            return Path(path_str).resolve()
    except Exception as e:
        raise ValueError(f"Invalid path format: {str(e)}")

def list_files(path_str: str, extension: str = None, recursive: bool = False) -> Dict:
    """List files with enhanced path handling"""
    try:
        try:
            path = normalize_path(path_str)
        except ValueError as e:
            return {"error": f"Error with path: {str(e)}"}
        
        if not path.exists():
            return {"error": f"Error: Path '{path}' does not exist"}
            
        # Add safety check for drive access
        if not any(path.drive.lower() == f"{d}:" for d in 'abcdefghijklmnopqrstuvwxyz'):
            return {"error": f"Error: Invalid drive in path '{path}'"}
        
        files = []
        normalized_ext = normalize_extension(extension) if extension else None
        pattern = f"*{normalized_ext}" if normalized_ext else "*"
        
        try:
            if recursive:
                file_paths = path.rglob(pattern)
            else:
                file_paths = path.glob(pattern)
                
            for file_path in file_paths:
                if file_path.is_file():
                    file_info = {
                        "file_name": file_path.name,
                        "date_created": datetime.fromtimestamp(file_path.stat().st_ctime).isoformat(),
                        "date_modified": datetime.fromtimestamp(file_path.stat().st_mtime).isoformat(),
                        "file_type": file_path.suffix
                    }
                    files.append(file_info)
            
            # Sort files for consistent output
            files.sort(key=lambda x: x["file_name"])
            
            return {
                "starting_path": str(path),
                "file_count": len(files),
                "files": files
            }
            
        except PermissionError:
            return {"error": f"Permission denied accessing some paths in '{path}'"}
        except Exception as e:
            return {"error": f"Error during file search in '{path}': {str(e)}"}
            
    except Exception as e:
        return {"error": f"Error with path handling: {str(e)}"}
    
def read_files(file_paths: List[str]) -> str:
    """Read a batch of one or more files and return their text with a delimiter"""
    result = []
    delimiter = "==========="
    for file_path_str in file_paths:
        try:
            file_path = Path(file_path_str).resolve()
            if not file_path.is_file():
                result.append(f"Error: '{file_path_str}' is not a valid file")
                continue
            with open(file_path, 'r', encoding='utf-8') as file:
                file_content = file.read()
                result.append(f"{delimiter}{file_path.as_posix()}\n{file_content}")
        except Exception as e:
            result.append(f"Error reading file '{file_path_str}': {str(e)}")
    return "\n".join(result)

def create_scratch_buffer_tool():
    return {
        "name": "add_to_scratch_buffer",
        "description": "Add a string to the scratch buffer",
        "parameters": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "The text to add to the scratch buffer"
                }
            },
            "required": ["text"]
        }
    }

def create_scratch_buffer_reader_tool():
    return {
        "name": "get_scratch_buffer",
        "description": "Retrieve the entire contents of the scratch buffer",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    }

scratch_buffer = ""

def add_to_scratch_buffer(text: str) -> None:
    """Add a string to the scratch buffer"""
    global scratch_buffer
    scratch_buffer += text + "\n\n"

def get_scratch_buffer() -> str:
    """Retrieve the entire contents of the scratch buffer"""
    return scratch_buffer

def create_tool_prompt(tools: List[Dict]):
    tool_descriptions = []
    for tool in tools:
        tool_descriptions.append(f"Use the function '{tool['name']}' to '{tool['description']}':\n{json.dumps(tool)}")
    
    tools_text = "\n\n".join(tool_descriptions)
    
    return f"""You have access to the following functions:

{tools_text}

If you choose to call a function ONLY reply in the following format with no prefix or suffix:

<function=example_function_name>{{"example_name": "example_value"}}</function>

Reminder:
- Function calls MUST follow the specified format, start with <function= and end with </function>
- Required parameters MUST be specified
- Only call one function at a time
- Put the entire function call reply on one line

Example usage for listing files:
- List all files in current directory: <function=list_directory>{{"path": "current"}}</function>
- List files in parent directory: <function=list_directory>{{"path": ".."}}</function>
- List files in drive root: <function=list_directory>{{"path": "D:"}}</function>
- Find all Python files recursively: <function=list_directory>{{"path": "current", "extension": ".py", "recursive": true}}</function>
- Find JavaScript files in specific directory: <function=list_directory>{{"path": "src", "extension": ".js"}}</function>
"""

def extract_function_call(response: str) -> tuple[str, dict]:
    """Extract function name and parameters from the model response more robustly"""
    try:
        # Handle case where closing tag is missing
        if response.startswith("<function="):
            # Extract function name
            start_idx = len("<function=")
            end_idx = response.find(">", start_idx)
            if end_idx == -1:
                raise ValueError("Invalid function call format - missing closing '>'")
            function_name = response[start_idx:end_idx]
            
            # Extract parameters - look for JSON object
            params_str = response[end_idx + 1:]
            # Remove closing tag if it exists
            params_str = params_str.split("</function>")[0]
            
            # If params_str is empty, return empty dict
            if not params_str.strip():
                return function_name, {}
            
            # Try to parse parameters as JSON
            try:
                params = json.loads(params_str)
                return function_name, params
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON parameters: {e}")
        else:
            raise ValueError("Response does not start with '<function='")
    except Exception as e:
        raise ValueError(f"Error parsing function call: {e}")

def execute_tool_call(response: str) -> str:
    """Execute the tool call with improved error handling"""
    try:
        function_name, params = extract_function_call(response)
        
        if function_name == "list_directory":
            files = list_files(
                params["path"],
                params.get("extension"),
                params.get("recursive", False)
            )
            return json.dumps(files, indent=2)
        elif function_name == "read_files":
            file_contents = read_files(params["file_paths"])
            return file_contents
        elif function_name == "add_to_scratch_buffer":
            add_to_scratch_buffer(params["text"])
            return "Text added to scratch buffer"
        elif function_name == "get_scratch_buffer":
            return get_scratch_buffer()
        else:
            return f"Unknown function: {function_name}"
    except ValueError as e:
        return f"Error parsing function call: {e}\nFull response: {response}"
    except Exception as e:
        return f"Error executing tool: {e}\nFull response: {response}"

def make_chat_request(prompt, api_url="http://127.0.0.1:1234/v1/chat/completions"):
    tools = [
        create_filesystem_tool(),
        create_file_reader_tool(),
        create_scratch_buffer_tool(),
        create_scratch_buffer_reader_tool()
    ]
    tool_prompt = create_tool_prompt(tools)
    
    headers = {
        "Content-Type": "application/json"
    }
    
    # Add system message to enforce proper function call format
    data = {
        "model": "llama-3.2-3b-instruct-uncensored",
        "messages": [
            {
                "role": "system",
                "content": "You must always include both opening and closing function tags. For example: <function=list_directory>{\"path\": \"current\"}</function>"
            },
            {
                "role": "user",
                "content": prompt
            },
            {
                "role": "user",
                "content": tool_prompt
            }
        ],
        "temperature": 0,
        "max_tokens": 1024,
        "stream": False
    }
    
    try:
        response = requests.post(api_url, headers=headers, json=data)
        response.raise_for_status()
        model_response = response.json()["choices"][0]["message"]["content"].strip()
        
        print("Debug - Model response:", model_response)  # Debug output
        
        # If the response looks like a function call, execute it
        if model_response.startswith("<function="):
            tool_result = execute_tool_call(model_response)            
            print("Debug - Scratch buffer:", scratch_buffer)
            return f"Model response: {model_response}\n\nTool execution result:\n{tool_result}"
        return model_response
        
    except requests.exceptions.RequestException as e:
        print(f"Error making request: {e}", file=sys.stderr)
        sys.exit(1)
    except (KeyError, IndexError) as e:
        print(f"Error parsing response: {e}", file=sys.stderr)
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="Test LLM tool usage with a local model")
    parser.add_argument("prompt", help="The prompt to send to the model")
    parser.add_argument("--api-url", default="http://127.0.0.1:1234/v1/chat/completions",
                      help="The API endpoint URL (default: http://127.0.0.1:1234/v1/chat/completions)")
    
    args = parser.parse_args()
    
    response = make_chat_request(args.prompt, args.api_url)
    print(response)

if __name__ == "__main__":
    main()