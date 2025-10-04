#!/usr/bin/env python3
"""
JS Path Extractor - Recursively extract paths from JavaScript files
"""

import os
import re
import sys
import argparse
import jsbeautifier
from urllib.parse import urljoin, urlparse


class Colors:
    """ANSI color codes for terminal output"""
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    BOLD = '\033[1m'
    DIM = '\033[2m'
    RESET = '\033[0m'


# Regex pattern to match paths/endpoints in JavaScript
PATH_REGEX = r"""
    (?:"|')                                 # Opening quote
    (
        (?:[a-zA-Z]{1,10}://|//)            # Full URL with scheme
        [^"'/]{1,}\.
        [a-zA-Z]{2,}[^"']{0,}
        |
        (?:/|\.\./|\./)                     # Relative paths
        [^"'><,;| *()(%%$^/\\\[\]]
        [^"'><,;|()]{1,}
        |
        [a-zA-Z0-9_\-/]{1,}/                # Endpoints with extensions
        [a-zA-Z0-9_\-/.]{1,}
        \.(?:[a-zA-Z]{1,4}|action)
        (?:[\?|#][^"|']{0,}|)
        |
        [a-zA-Z0-9_\-/]{1,}/                # REST API endpoints
        [a-zA-Z0-9_\-/]{3,}
        (?:[\?|#][^"|']{0,}|)
        |
        [a-zA-Z0-9_\-]{1,}                  # Filenames
        \.(?:php|asp|aspx|jsp|json|action|html|js|txt|xml)
        (?:[\?|#][^"|']{0,}|)
    )
    (?:"|')                                 # Closing quote
"""


def find_js_files(directory):
    """Recursively find all .js files in a directory"""
    js_files = []
    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith('.js'):
                js_files.append(os.path.join(root, file))
    return sorted(js_files)


def extract_base_url_from_path(js_file_path):
    """Extract base URL from the JS file path structure"""
    # Normalize path separators
    normalized_path = js_file_path.replace('\\', '/')
    
    # Look for domain pattern in the path
    # Pattern: results/js_files/domain.com/file.js
    parts = normalized_path.split('/')
    
    # Find the part that looks like a domain
    domain = None
    js_relative_path = ""
    
    for i, part in enumerate(parts):
        # Check if this part looks like a domain (contains dots and valid characters)
        if '.' in part and re.match(r'^[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', part):
            domain = part
            # Get the remaining path after the domain
            if i + 1 < len(parts):
                js_relative_path = '/'.join(parts[i+1:])
            break
    
    if domain:
        # Construct the full URL to the JS file
        base_url = f"https://{domain}/"
        js_full_url = f"https://{domain}/{js_relative_path}"
        
        # Extract the directory part from the JS file URL for relative path resolution
        js_dir_url = js_full_url.rsplit('/', 1)[0] + '/'
        
        return base_url, js_dir_url
    
    return None, None


def rebuild_paths(base_url, js_dir_url, relative_path):
    """Generate all possible URLs by progressively trimming directory levels"""
    urls = []
    
    # Clean up the relative path (remove ./ prefix)
    clean_path = relative_path
    if clean_path.startswith('./'):
        clean_path = clean_path[2:]
    elif clean_path.startswith('.'):
        clean_path = clean_path[1:]
    
    # Start from the JS file directory and work backwards
    current_url = js_dir_url
    
    while True:
        # Combine current directory URL with the clean path
        if current_url.endswith('/'):
            full_url = current_url + clean_path
        else:
            full_url = current_url + '/' + clean_path
        
        urls.append(full_url)
        
        # Check if we've reached the base URL - but do this AFTER adding the URL
        if current_url.rstrip('/') == base_url.rstrip('/'):
            break
            
        current_url = current_url.rstrip('/')
        last_slash = current_url.rfind('/')
        
        # Make sure we don't go beyond the base URL
        if last_slash == -1:
            break
            
        # Extract the base without trailing slash to compare properly
        base_without_slash = base_url.rstrip('/')
        next_url = current_url[:last_slash+1]
        
        # If the next step would take us before the base URL, break
        if len(next_url.rstrip('/')) < len(base_without_slash):
            break
            
        current_url = next_url

    return urls


def is_mime_type(text):
    """Check if text is a MIME type (e.g., audio/ogg, text/plain)"""
    mime_pattern = r'^[a-z]+/[a-z0-9\-\+\.]+$'
    return re.match(mime_pattern, text, re.IGNORECASE) is not None


def extract_paths(content, custom_regex=None):
    """Extract paths from JavaScript content"""
    # Beautify code for better parsing
    try:
        if len(content) > 1000000:
            content = content.replace(";", ";\n").replace(",", ",\n")
        else:
            content = jsbeautifier.beautify(content)
    except:
        pass  # Continue with original content if beautification fails
    
    # Find all matches
    regex = re.compile(custom_regex if custom_regex else PATH_REGEX, re.VERBOSE)
    all_matches = []
    
    for match in regex.finditer(content):
        path = match.group(1)
        if path:
            # Skip MIME types
            if is_mime_type(path):
                continue
                
            # Skip certain patterns
            skip_patterns = [
                r'^[a-zA-Z]$',  # Single letters
                r'^[0-9]+$',    # Only numbers
                r'^\w+$' if len(path) < 3 else None,  # Very short words
            ]
            
            should_skip = False
            for pattern in skip_patterns:
                if pattern and re.match(pattern, path):
                    should_skip = True
                    break
            
            if not should_skip:
                all_matches.append(path)
    
    # Remove duplicates while preserving order
    unique_paths = []
    seen = set()
    for path in all_matches:
        if path not in seen:
            unique_paths.append(path)
            seen.add(path)
    
    return unique_paths


def read_file(filepath):
    """Read file content with proper encoding handling"""
    encodings = ['utf-8', 'utf-16', 'latin-1', 'cp1252']
    
    for encoding in encodings:
        try:
            with open(filepath, 'r', encoding=encoding) as f:
                return f.read()
        except (UnicodeDecodeError, UnicodeError):
            continue
        except Exception as e:
            print(f"{Colors.RED}Error reading {filepath}: {e}{Colors.RESET}")
            return None
    
    print(f"{Colors.YELLOW}Warning: Could not decode {filepath}{Colors.RESET}")
    return None


def write_output_file(results, output_file):
    """Write results to output file"""
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            for js_file, paths in results.items():
                f.write(f"\n{'='*80}\n")
                f.write(f"File: {js_file}\n")
                f.write(f"{'='*80}\n")
                for path in paths:
                    f.write(f"{path}\n")
        
        print(f"{Colors.GREEN}Results saved to: {output_file}{Colors.RESET}")
    except Exception as e:
        print(f"{Colors.RED}Error writing output file: {e}{Colors.RESET}")


def write_path_rebuild_file(results, output_dir="."):
    """Write path rebuild file with reconstructed URLs"""
    rebuild_file = os.path.join(output_dir, "new_path_rebuild")
    
    try:
        with open(rebuild_file, 'w', encoding='utf-8') as f:
            for js_file, paths in results.items():
                # Extract base URL from JS file path
                base_url, js_dir_url = extract_base_url_from_path(js_file)
                
                if not base_url:
                    continue
                
                for path in paths:
                    # Only process relative paths that start with "."
                    if path.startswith('.'):
                        # Remove spaces from the path
                        clean_path = path.replace(' ', '')
                        
                        # Remove relative path prefixes
                        if clean_path.startswith('./'):
                            clean_path = clean_path[2:]  # Remove "./"
                        elif clean_path.startswith('../'):
                            clean_path = clean_path[3:]  # Remove "../"
                        elif clean_path.startswith('.'):
                            clean_path = clean_path[1:]  # Remove "."
                        
                        rebuilt_urls = rebuild_paths(base_url, js_dir_url, clean_path)
                        for url in rebuilt_urls:
                            f.write(f"{url}\n")
    except Exception as e:
        print(f"{Colors.RED}Error writing rebuild file: {e}{Colors.RESET}")

def main():
    parser = argparse.ArgumentParser(
        description="Extract paths from JavaScript files and generate rebuild URLs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s -i results/js_files/
  %(prog)s -i results/js_files/ -o output.txt
  %(prog)s -i results/js_files/ --rebuild-only
        """
    )
    
    parser.add_argument('-i', '--input', required=True,
                      help='Input directory containing JS files')
    parser.add_argument('-o', '--output',
                      help='Output file for extracted paths')
    parser.add_argument('-r', '--regex',
                      help='Custom regex pattern for path extraction')
    parser.add_argument('--rebuild-only', action='store_true',
                      help='Only generate new_path_rebuild file')
    
    args = parser.parse_args()
    
    # Validate input
    if not os.path.exists(args.input):
        print(f"{Colors.RED}Error: Directory not found: {args.input}{Colors.RESET}")
        sys.exit(1)
    
    if not os.path.isdir(args.input):
        print(f"{Colors.RED}Error: Not a directory: {args.input}{Colors.RESET}")
        sys.exit(1)
    
    # Find JS files
    print(f"{Colors.BLUE}Scanning: {args.input}{Colors.RESET}")
    js_files = find_js_files(args.input)
    
    if not js_files:
        print(f"{Colors.YELLOW}No JavaScript files found{Colors.RESET}")
        sys.exit(0)
    
    print(f"{Colors.YELLOW}Found {len(js_files)} JS file(s){Colors.RESET}\n")
    
    # Process each file
    results = {}
    total_paths = 0
    
    for js_file in js_files:
        content = read_file(js_file)
        if content is None:
            continue
        
        paths = extract_paths(content, args.regex)
        if paths:
            results[js_file] = paths
            total_paths += len(paths)
            
            # Show results immediately in terminal (unless rebuild-only mode)
            if not args.rebuild_only:
                print(f"\n{Colors.CYAN}{Colors.BOLD}{js_file}{Colors.RESET}")
                for path in paths:
                    print(f"  {Colors.GREEN}→{Colors.RESET} {path}")
    
    # Output results
    if not results:
        print(f"\n{Colors.YELLOW}No paths found in any files{Colors.RESET}")
        sys.exit(0)
    
    # Always generate new_path_rebuild file
    output_dir = os.path.dirname(args.output) if args.output else "."
    write_path_rebuild_file(results, output_dir)
    
    # Save to regular output file if requested (and not in rebuild-only mode)
    if args.output and not args.rebuild_only:
        write_output_file(results, args.output)
    
    # Summary (unless rebuild-only mode)
    if not args.rebuild_only:
        print(f"\n{Colors.BOLD}{Colors.GREEN}✓ Complete!{Colors.RESET}")
        print(f"{Colors.DIM}Files with paths: {len(results)} | Total paths: {total_paths}{Colors.RESET}")


if __name__ == "__main__":
    main()
