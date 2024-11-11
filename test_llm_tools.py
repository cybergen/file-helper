#!/usr/bin/env python3
import requests
import json
import argparse
import sys
import os
from typing import List, Dict
from pathlib import Path

def create_weather_tool():
    return {
        "name": "get_current_weather",
        "description": "Get the current weather in a given location",
        "parameters": {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "The city and state, e.g. San Francisco, CA",
                }
            },
            "required": ["location"],
        }
    }

def create_filesystem_tool():
    return {
        "name": "list_directory",
        "description": "List all files in a directory, optionally filtering by file extension",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The directory path to search in (use 'current' for current directory)"
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

def normalize_extension(extension: str) -> str:
    """Normalize file extension to include the dot and lowercase"""
    if not extension:
        return ""
    ext = extension.lower()
    return f".{ext.lstrip('.')}"

def list_files(path_str: str, extension: str = None, recursive: bool = False) -> List[str]:
    """List files with improved path handling"""
    try:
        # Handle special 'current' keyword
        if path_str.lower() in ['current', '.', '']:
            path = Path.cwd()
        else:
            path = Path(path_str)

        # Convert to absolute path
        path = path.resolve()
        
        if not path.exists():
            return [f"Error: Path '{path}' does not exist"]
        
        files = []
        normalized_ext = normalize_extension(extension) if extension else None
        
        # Define pattern for matching files
        pattern = f"*{normalized_ext}" if normalized_ext else "*"
        
        try:
            if recursive:
                file_paths = path.rglob(pattern)
            else:
                file_paths = path.glob(pattern)
                
            # Convert to list and filter for files only
            files = [str(f) for f in file_paths if f.is_file()]
            
            # Sort files for consistent output
            files.sort()
            
            if not files:
                return [f"No files found matching pattern{f' with extension {normalized_ext}' if normalized_ext else ''}"]
                
            return files
            
        except Exception as e:
            return [f"Error during file search: {str(e)}"]
            
    except Exception as e:
        return [f"Error with path handling: {str(e)}"]

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
- If looking for real time information use relevant functions before falling back to brave_search
- Function calls MUST follow the specified format, start with <function= and end with </function>
- Required parameters MUST be specified
- Only call one function at a time
- Put the entire function call reply on one line

Example usage for listing files:
- List all files in current directory: <function=list_directory>{{"path": "current"}}</function>
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
        elif function_name == "get_current_weather":
            return f"Would fetch weather for: {params['location']}"
        else:
            return f"Unknown function: {function_name}"
    except ValueError as e:
        return f"Error parsing function call: {e}\nFull response: {response}"
    except Exception as e:
        return f"Error executing tool: {e}\nFull response: {response}"

def make_chat_request(prompt, api_url="http://127.0.0.1:1234/v1/chat/completions"):
    tools = [create_weather_tool(), create_filesystem_tool()]
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