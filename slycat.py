#!/usr/bin/env python3

import os
import re
import argparse
import fnmatch

# --- Added Section: AI Instruction Prompt ---
# Define the prompt string to guide AI formatting. (Idea suggested by Gemini)
AI_INSTRUCTION_PROMPT = """
> **AI Instruction:**
> The following code represents a software project, with each file presented below its corresponding path header.
>
> Please adhere strictly to the following format when generating responses or modifications:
> 1.  Use a header line exactly like `### **\`path/to/file.ext\`**` before each file's content. Replace `path/to/file.ext` with the actual relative path.
> 2.  Enclose all code blocks within triple backticks (```) specifying the language identifier (e.g., ```python, ```javascript, ```html, etc.). If the language is unknown or plain text, you can omit it or use ```text.
>
> Maintaining this exact structure is crucial for parsing your response correctly. Thank you!

""" # Add a couple of newlines for separation after the prompt
AI_INSTRUCTION_PROMPT += "\n\n"
# --- End Added Section ---


# Dictionary mapping file extensions to corresponding code fence languages
CODE_FENCE_LOOKUP = {
    ".py": "python",
    ".js": "javascript",
    ".html": "html",
    ".css": "css",
    ".sh": "bash",
    ".java": "java",
    ".cpp": "c++",
    ".c": "c",
    ".json": "json",
    ".yml": "yaml",
    ".yaml": "yaml",
    ".xml": "xml",
    ".rb": "ruby",
    ".rs": "rust",
    ".go": "go",
    ".md": "markdown", # Changed from md to markdown for clarity
    ".txt": "text",  # Explicitly 'text' for clarity
    ".ini": "ini",
    ".cfg": "ini", # Often treated as ini
    # Add more as needed
}

def handle_error(error_message):
    """Prints an error message and exits the program.

    Args:
        error_message (str): The error message to display.
    """
    print(f"Error: {error_message}")
    exit(1)

def is_text_file(file_path):
    """
    Checks if a file is likely a text file based on its content.

    This function attempts to read the first few bytes of the file and checks
    for the presence of null bytes or control characters, which are typically
    found in binary files. It also excludes files with certain extensions that
    are known to be binary.

    Args:
        file_path (str): Path to the file.

    Returns:
        bool: True if it's likely a text file, False otherwise.
    """

    # Exclude files based on known binary extensions
    binary_extensions = {
        '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.ico', # Images
        '.mp3', '.wav', '.ogg', '.flac', '.aac', # Audio
        '.mp4', '.avi', '.mov', '.mkv', '.webm', # Video
        '.zip', '.rar', '.7z', '.tar', '.gz', '.bz2', '.xz', # Archives
        '.exe', '.dll', '.so', '.o', '.pyc', '.pyd', # Executables and object files
        '.class', '.jar', '.war', # Java binaries
        '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', # Documents
        '.db', '.sqlite', '.sqlite3', # Databases
        '.woff', '.woff2', '.ttf', '.otf', '.eot' # Fonts
        # Add more as needed
    }
    _, ext = os.path.splitext(file_path)
    if ext.lower() in binary_extensions:
        return False

    # Check for null bytes and control characters
    try:
        with open(file_path, 'rb') as f:
            # Read a decent chunk to catch potential binary data later in the file
            chunk = f.read(4096)
            if not chunk: # Empty file is considered text
                return True
            # Check for null bytes
            if b'\x00' in chunk:
                return False
            # Check for excessive non-printable/control characters (excluding whitespace)
            # Allows ASCII text, UTF-8 multi-byte chars (which won't be < 32 unless control chars)
            # Allows tab (9), newline (10), carriage return (13)
            control_chars = sum(1 for byte in chunk if byte < 32 and byte not in (9, 10, 13))
            # Heuristic: if more than 10% of the chunk are non-whitespace control chars, likely binary
            if control_chars / len(chunk) > 0.1:
                 return False
            return True # Likely text
    except Exception as e:
        print(f"  Warning: Could not read {file_path} to check type ({e}), skipping.")
        return False


def write_file_to_output(file_path, base_folder, output_file):
    """Writes the content of a file to the output file with markdown code fences.

    Args:
        file_path (str): Path to the file.
        base_folder (str): Base folder for relative path calculation.
        output_file (file object): Output file object.
    """
    # Calculate the relative path including the base_folder name
    rel_path = os.path.relpath(file_path, base_folder)
    base_folder_name = os.path.basename(os.path.normpath(base_folder)) # Use normpath to handle trailing slashes
    if base_folder_name and base_folder_name != '.': # Avoid adding '.' as base folder
        rel_path = os.path.join(base_folder_name, rel_path)
    else:
        # If base_folder is '.' or empty, rel_path might start with '..' if file is outside.
        # Use normpath to clean it up.
        rel_path = os.path.normpath(rel_path)

    # Ensure consistent path separators (Unix-style) for cross-platform readability
    rel_path = rel_path.replace(os.sep, '/')

    _, ext = os.path.splitext(file_path)
    language = CODE_FENCE_LOOKUP.get(ext.lower(), "text") # Default to 'text'

    # Attempt to read the file with different encodings
    encodings_to_try = ['utf-8', 'latin-1', 'ascii'] # Prioritize UTF-8
    content = None
    detected_encoding = None
    for encoding in encodings_to_try:
        try:
            with open(file_path, 'r', encoding=encoding) as f:
                content = f.read()
            detected_encoding = encoding
            break  # Stop trying encodings once successful
        except UnicodeDecodeError:
            continue
        except Exception as e: # Catch other file reading errors
             print(f"  Warning: Error reading {file_path} with {encoding}: {e}. Trying next encoding.")
             continue

    if content is None:
        print(f"  Warning: Unable to decode {file_path} with attempted encodings ({', '.join(encodings_to_try)}). Skipping file.")
        return # Skip writing this file

    # Write the standardized header and fenced code block
    output_file.write(f"### **`{rel_path}`**\n\n```{language}\n{content}\n```\n\n") # Add extra newline for spacing

def should_include(item_path, includes, is_dir):
    """Checks if a file/directory path should be included based on patterns.

    Args:
        item_path (str): Full path to the item.
        includes (list): List of include patterns (globs).
        is_dir (bool): True if item_path is a directory.

    Returns:
        bool: True if the item should be included.
    """
    if not includes:
        return True  # Include everything if no include patterns specified

    # Match against the full path or just the basename depending on pattern
    for pattern in includes:
        if fnmatch.fnmatch(item_path, pattern) or fnmatch.fnmatch(os.path.basename(item_path), pattern):
             # If it's a directory match, we want to include it and its contents
             # If it's a file match, we want to include it
            return True
    return False


def should_exclude(item_path, exclusions, is_dir):
    """Checks if a file/directory path should be excluded based on patterns.

    Args:
        item_path (str): Full path to the item.
        exclusions (list): List of exclusion patterns (globs).
        is_dir (bool): True if item_path is a directory.

    Returns:
        bool: True if the item should be excluded.
    """
    # Match against the full path or just the basename
    for pattern in exclusions:
         # Check full path match first (e.g., exclude 'src/temp/*')
        if fnmatch.fnmatch(item_path, pattern):
            return True
        # Check basename match (e.g., exclude '*.log' or '.git')
        if fnmatch.fnmatch(os.path.basename(item_path), pattern):
            return True
        # Special handling for directory patterns ending with /
        if is_dir and pattern.endswith(('/', os.sep)) and fnmatch.fnmatch(item_path + os.sep, pattern):
             return True

    return False


def traverse_and_concatenate(current_path, base_folder, output_file, exclusions, includes, processed_files, skipped_files, excluded_items):
    """Recursively traverses directories and writes files to the output file.

    Args:
        current_path (str): Current directory or file to process.
        base_folder (str): The initial base folder from command line for relative paths.
        output_file (file object): Output file object.
        exclusions (list): List of exclusion patterns.
        includes (list): List of inclusion patterns.
        processed_files (set): Set to store paths of processed text files.
        skipped_files (set): Set to store paths of skipped non-text files.
        excluded_items (set): Set to store paths of explicitly excluded items.
    """
    is_dir = os.path.isdir(current_path)
    rel_path_to_base = os.path.relpath(current_path, base_folder) # Path relative to the *initial* base
    normalized_rel_path = rel_path_to_base.replace(os.sep, '/')

    # 1. Check Exclusions first
    if should_exclude(current_path, exclusions, is_dir):
        print(f"  Excluding: {normalized_rel_path}{'/' if is_dir else ''}")
        excluded_items.add(current_path)
        return

    # 2. Check Inclusions
    # An item must match *an* include pattern if include patterns are specified.
    if includes and not should_include(current_path, includes, is_dir):
         # If it's a directory that doesn't match, we still need to check its children
         # against the include patterns, unless the directory itself was excluded above.
        if is_dir:
            try:
                # Sort items for consistent order
                items = sorted(os.listdir(current_path))
                for item in items:
                    item_path = os.path.join(current_path, item)
                    traverse_and_concatenate(item_path, base_folder, output_file, exclusions, includes, processed_files, skipped_files, excluded_items)
            except OSError as e:
                print(f"  Warning: Cannot access {current_path}: {e}. Skipping.")
        # If it's a file that doesn't match include patterns, just return
        else:
            # We don't necessarily print 'excluding' here as it wasn't explicitly excluded by -x,
            # it just didn't match any -i patterns.
            pass
        return # Stop processing this path if it doesn't match includes (and includes are specified)

    # 3. Process the item (if not excluded and matches includes if specified)
    if is_dir:
        print(f"  Entering: {normalized_rel_path}/")
        try:
            # Sort items for consistent order
            items = sorted(os.listdir(current_path))
            for item in items:
                item_path = os.path.join(current_path, item)
                # Recursive call - pass the *original* base_folder for consistent relative paths
                traverse_and_concatenate(item_path, base_folder, output_file, exclusions, includes, processed_files, skipped_files, excluded_items)
        except OSError as e:
            print(f"  Warning: Cannot access contents of {current_path}: {e}. Skipping.")

    elif os.path.isfile(current_path):
        if is_text_file(current_path):
            display_path = os.path.relpath(current_path, start=os.path.dirname(base_folder) if base_folder != '.' else '.')
            display_path = display_path.replace(os.sep, '/')
            print(f"  Adding:   {display_path}")
            processed_files.add(current_path)
            # Pass the *original* base_folder for consistent relative paths
            write_file_to_output(current_path, base_folder, output_file)
        else:
            display_path = os.path.relpath(current_path, start=os.path.dirname(base_folder) if base_folder != '.' else '.')
            display_path = display_path.replace(os.sep, '/')
            print(f"  Skipping (non-text): {display_path}")
            skipped_files.add(current_path)


def concatenate_files_and_folders(output_name, paths, force=False, exclusions=[], includes=[], add_prompt=False):
    """Concatenates text files and folders into a single output file with markdown code fences.

    Args:
        output_name (str): Name of the output file.
        paths (list): List of file and folder paths to concatenate.
        force (bool): Overwrite the output file if it exists.
        exclusions (list): List of exclusion patterns.
        includes (list): List of inclusion patterns.
        add_prompt (bool): Whether to add the AI instruction prompt.
    """
    output_name = os.path.normpath(output_name)
    if os.path.exists(output_name) and not force:
        # Check if output file is one of the input paths to prevent self-concatenation issues
        normalized_input_paths = {os.path.normpath(p) for p in paths}
        if output_name in normalized_input_paths:
             handle_error(f"Output file '{output_name}' is also an input path. Cannot concatenate file into itself without --force.")
        handle_error(f"Output file '{output_name}' already exists. Use -f or --force to overwrite.")
    elif os.path.exists(output_name) and force:
        print(f"Overwriting existing file: {output_name}")


    processed_files = set()  # Use sets for efficiency
    skipped_files = set()
    excluded_items = set()
    not_found_paths = []

    # Add common virtual environment patterns to default exclusions if not overridden
    # Making exclusions a set avoids duplicates if user specifies them too
    effective_exclusions = set(exclusions)
    default_venv_patterns = {'venv', '.venv', '**/site-packages', '__pycache__', '*.pyc', '.git', '.hg', '.svn', 'node_modules', '.DS_Store'}
    effective_exclusions.update(default_venv_patterns)
    # Convert back to list for the functions expecting lists
    effective_exclusions_list = list(effective_exclusions)


    with open(output_name, 'w', encoding='utf-8') as output_file:
        # --- Write AI Prompt if requested ---
        if add_prompt:
            # Add the instruction prompt for AI (Idea suggested by Gemini)
            print("  Adding AI instruction prompt...")
            output_file.write(AI_INSTRUCTION_PROMPT)
        # --- End Prompt Section ---

        for path_arg in paths:
            if not os.path.exists(path_arg):
                print(f"Warning: Input path '{path_arg}' does not exist. Skipping.")
                not_found_paths.append(path_arg)
                continue

            path_arg = os.path.normpath(path_arg)

             # Determine the base folder for relative path calculations.
             # If path_arg is a file, base is its directory.
             # If path_arg is a directory, base is that directory itself.
            if os.path.isfile(path_arg):
                base_folder_for_relpath = os.path.dirname(path_arg)
                 # Handle case where file is in the current directory
                if not base_folder_for_relpath:
                    base_folder_for_relpath = '.'
            else: # is directory
                base_folder_for_relpath = path_arg


            traverse_and_concatenate(path_arg, base_folder_for_relpath, output_file, effective_exclusions_list, includes, processed_files, skipped_files, excluded_items)


    print("\nConcatenation complete.")
    print("\nSummary:")
    print(f"  Output file: {output_name}")
    if not_found_paths:
        print(f"  Paths not found: {len(not_found_paths)}")
    print(f"  Text files added: {len(processed_files)}")
    if skipped_files:
        print(f"  Skipped non-text files: {len(skipped_files)}")
    # Report excluded items based on patterns, not just skipped directories during traversal
    explicitly_excluded_count = sum(1 for item in excluded_items if should_exclude(item, effective_exclusions_list, os.path.isdir(item)))
    if explicitly_excluded_count > 0:
         print(f"  Items excluded by patterns: {explicitly_excluded_count}")
    elif exclusions: # If user provided exclusions but none matched
         print(f"  Items excluded by patterns: 0")


def slice_files(input_files, output_folder):
    """Slices a concatenated file back into individual files and folders.

    Args:
        input_files (list): List of input files to slice.
        output_folder (str): Path to the output folder.
    """
    print(f"Slicing files: {', '.join(input_files)}")
    print(f"Output folder: {output_folder}")

    if not os.path.exists(output_folder):
        try:
            os.makedirs(output_folder)
            print(f"Created output folder: {output_folder}")
        except OSError as e:
            handle_error(f"Could not create output folder '{output_folder}': {e}")

    # Regular expression to match file sections:
    # Captures: 1=filepath, 2=language(optional), 3=content
    # Handles optional language tag and potential whitespace variations
    # Uses non-greedy matching for content ([\s\S]*?)
    pattern = r'^\s*###\s*\*\*`([^`]+)`\*\*\s*$\n+```(?:(\w*|\S*)\n)?([\s\S]*?)\n```'

    files_created = 0
    errors_encountered = 0

    for input_file in input_files:
        if not os.path.isfile(input_file):
            print(f"Warning: Input file '{input_file}' not found. Skipping.")
            errors_encountered += 1
            continue

        print(f"Processing '{input_file}'...")
        try:
            # Try reading with UTF-8 first, then latin-1 as fallback
            content = None
            try:
                with open(input_file, 'r', encoding='utf-8') as f:
                    content = f.read()
            except UnicodeDecodeError:
                print(f"  Warning: '{input_file}' is not UTF-8. Trying latin-1...")
                try:
                     with open(input_file, 'r', encoding='latin-1') as f:
                         content = f.read()
                except Exception as e:
                     print(f"  Error reading '{input_file}' with latin-1: {e}. Skipping this file.")
                     errors_encountered += 1
                     continue
            except Exception as e:
                 print(f"  Error reading '{input_file}': {e}. Skipping this file.")
                 errors_encountered += 1
                 continue

            if content is None:
                 continue # Skip if file couldn't be read

            # Ignore the AI instruction prompt if present at the beginning
            prompt_marker = "> **AI Instruction:**"
            if content.lstrip().startswith(prompt_marker):
                try:
                    # Find the end of the prompt blockquote section
                    prompt_end_index = content.find("\n\n", content.find(prompt_marker)) + 2
                    if prompt_end_index > 1: # Check if found
                        content = content[prompt_end_index:]
                        print("  Skipped AI instruction prompt.")
                    else: # Fallback if structure is unexpected
                         print("  Warning: Found AI prompt marker but couldn't reliably determine its end. Proceeding with full content.")
                except Exception:
                     print("  Warning: Error trying to skip AI prompt. Proceeding with full content.")


            matches = re.finditer(pattern, content, re.MULTILINE)
            match_count = 0

            for match in matches:
                match_count += 1
                # Use os.path.join for creating paths, normpath to clean up separators
                rel_path = os.path.normpath(match.group(1).strip())
                # Ensure we don't allow absolute paths or escaping the output folder
                if os.path.isabs(rel_path) or '..' in rel_path.split(os.sep):
                     print(f"  Security Warning: Skipping potentially unsafe path '{rel_path}' found in '{input_file}'.")
                     errors_encountered += 1
                     continue

                file_content = match.group(3) # Content is group 3 now
                full_output_path = os.path.join(output_folder, rel_path)

                try:
                    # Create parent directories if they don't exist
                    os.makedirs(os.path.dirname(full_output_path), exist_ok=True)

                    display_path = os.path.normpath(full_output_path)
                    print(f"  Creating file: {display_path}")
                    with open(full_output_path, 'w', encoding='utf-8') as output_file:
                        # Strip potential leading/trailing whitespace artifact from regex capture if needed
                        output_file.write(file_content) # removed .strip() - keep original whitespace
                    files_created += 1
                except OSError as e:
                    print(f"  Error creating file {full_output_path}: {e}")
                    errors_encountered += 1
                except Exception as e: # Catch unexpected errors
                     print(f"  Unexpected error processing path '{rel_path}': {e}")
                     errors_encountered += 1


            if match_count == 0:
                 print(f"  Warning: No file sections found in '{input_file}'. Does it contain the correct '### **`path`**' and '```' format?")


        except Exception as e:
            print(f"  Error processing input file '{input_file}': {e}")
            errors_encountered += 1


    print("\nSlicing complete.")
    print(f"  Files created: {files_created}")
    if errors_encountered > 0:
         print(f"  Errors encountered: {errors_encountered}")


def main():
    """Main function to handle command-line arguments and execute concatenation or slicing."""
    parser = argparse.ArgumentParser(
        description="Concatenate (bundle) or slice (unbundle) text files from project structures into/from a single Markdown file.",
        formatter_class=argparse.RawTextHelpFormatter # Keep formatting in help text
    )
    parser.add_argument(
        "output",
        help="Concatenate mode: Name of the output Markdown file.\nSlice mode: Path to the output folder where files will be recreated."
    )
    parser.add_argument(
        "paths",
        nargs="+",
        help="Concatenate mode: Files and/or folders to include in the bundle.\nSlice mode: One or more concatenated Markdown files to slice."
    )
    parser.add_argument(
        "-f", "--force",
        action="store_true",
        help="Concatenate mode: Overwrite the output file if it exists."
    )
    parser.add_argument(
        "-s", "--slice",
        action="store_true",
        help="Run in slice mode: Recreate files/folders from the input Markdown file(s)."
    )
    parser.add_argument(
        "-x", "--exclude",
        action="append",
        default=[], # Will be augmented with defaults later
        help="Exclude files or folders matching the given pattern (glob-style, e.g., '*.log', '.git', 'build/').\nCan be used multiple times.\nDefaults include common patterns like .git, venv, node_modules, __pycache__, etc."
    )
    parser.add_argument(
        "-i", "--include",
        action="append",
        default=[],
        help="Include only files or folders matching the given pattern (glob-style).\nIf used, only items matching these patterns will be considered.\nCan be used multiple times."
    )
    # --- Added Argument ---
    parser.add_argument(
        "-p", "--add-prompt",
        action="store_true",
        help="Concatenate mode: Add an instruction prompt for AI at the beginning of the output file\nto encourage maintaining the correct format."
    )
    # --- End Added Argument ---

    args = parser.parse_args()

    # Basic validation: Cannot use --add-prompt or --force in slice mode
    if args.slice:
        if args.add_prompt:
            handle_error("--add-prompt is only valid in concatenate mode.")
        if args.force:
             print("Warning: --force has no effect in slice mode.") # Slice mode creates/overwrites files individually

    else: # Concatenate mode validation
        # Check for duplicate names between files and folders in direct input paths
        # Note: traverse function handles deeper conflicts
        input_files = []
        input_folders = []
        for path in args.paths:
             # Check existence here before categorizing
            if not os.path.exists(path):
                 # Warning printed later in concatenate function, just skip categorization here
                continue
            if os.path.isfile(path):
                input_files.append(os.path.normpath(path))
            elif os.path.isdir(path):
                input_folders.append(os.path.normpath(path))
            # Ignore others (sockets, etc.) - handled by traversal function too

        file_basenames = {os.path.basename(f) for f in input_files}
        folder_basenames = {os.path.basename(d) for d in input_folders}

        common_basenames = file_basenames.intersection(folder_basenames)
        if common_basenames:
            # This check might be overly strict depending on use case, could be warning
            print(f"Warning: The following base names appear as both files and folders in direct input: {', '.join(common_basenames)}")
            # handle_error(f"The following base names appear as both files and folders in direct input: {', '.join(common_basenames)}")


    if args.slice:
        print("Running in slice mode...")
        slice_files(args.paths, args.output)
    else:
        print("Running in concatenate mode...")
        # Pass the add_prompt argument
        concatenate_files_and_folders(
            args.output,
            args.paths,
            force=args.force,
            exclusions=args.exclude,
            includes=args.include,
            add_prompt=args.add_prompt # Pass the new flag
        )

if __name__ == "__main__":
    main()
