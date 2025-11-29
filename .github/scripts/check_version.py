#!/usr/bin/env python3
"""
Script to check if a new version of IB API is available and optionally update.
Used by GitHub Actions workflow to check for updates and perform updates.
"""

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path
from urllib.parse import urljoin, urlparse

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("Error: Required packages not installed.")
    print("Please install: pip install requests beautifulsoup4")
    sys.exit(1)


def find_download_url_and_version(version_type):
    """
    Parse the Interactive Brokers download page to find the Mac/Unix download URL and version number.
    
    Args:
        version_type: 'stable' or 'latest'
    
    Returns:
        tuple: (download_url, version_number) where version_number is like "10.37" or "10.41"
    """
    url = "https://interactivebrokers.github.io/#"
    
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"Error fetching download page: {e}")
        sys.exit(1)
    
    soup = BeautifulSoup(response.content, 'html.parser')
    
    # Find all links in the page
    links = soup.find_all('a', href=True)
    
    download_url = None
    version_number = None
    
    for link in links:
        # Look for Mac/Unix download links
        href = link.get('href', '')
        if 'twsapi_macunix' in href and '.zip' in href:
            # Check if this is the right version by looking at parent context
            parent_row = link.find_parent('tr')
            if parent_row:
                row_text = parent_row.get_text()
                if version_type == 'stable' and 'TWS API Stable' in row_text:
                    download_url = href
                    # Extract version number from the row text (e.g., "API 10.37")
                    version_match = re.search(r'API\s+(\d+\.\d+)', row_text)
                    if version_match:
                        version_number = version_match.group(1)
                    break
                elif version_type == 'latest' and 'TWS API Latest' in row_text:
                    download_url = href
                    # Extract version number from the row text (e.g., "API 10.41")
                    version_match = re.search(r'API\s+(\d+\.\d+)', row_text)
                    if version_match:
                        version_number = version_match.group(1)
                    break
    
    if not download_url:
        print(f"Error: Could not find {version_type} Mac/Unix download URL")
        sys.exit(1)
    
    if not version_number:
        # Try to extract from filename as fallback
        filename_match = re.search(r'twsapi_macunix\.(\d+)\.(\d+)', download_url)
        if filename_match:
            version_number = f"{filename_match.group(1)}.{filename_match.group(2)}"
    
    # Handle protocol-relative URLs
    if download_url.startswith('//'):
        download_url = 'https:' + download_url
    elif download_url.startswith('/'):
        download_url = urljoin('https://interactivebrokers.github.io', download_url)
    
    return download_url, version_number


def download_file(url, dest_path):
    """
    Download a file from URL to destination path.
    
    Args:
        url: URL to download from
        dest_path: Path to save the file
    
    Returns:
        Path: Path to downloaded file
    """
    print(f"Downloading {url}...")
    try:
        response = requests.get(url, stream=True, timeout=60)
        response.raise_for_status()
        
        total_size = int(response.headers.get('content-length', 0))
        downloaded = 0
        
        with open(dest_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_size > 0:
                        percent = (downloaded / total_size) * 100
                        print(f"\rProgress: {percent:.1f}%", end='', flush=True)
        
        print()  # New line after progress
        print(f"Download complete: {dest_path}")
        return Path(dest_path)
    except requests.RequestException as e:
        print(f"Error downloading file: {e}")
        sys.exit(1)


def extract_zip(zip_path, extract_dir):
    """
    Extract ZIP file to directory.
    
    Args:
        zip_path: Path to ZIP file
        extract_dir: Directory to extract to
    
    Returns:
        Path: Path to extracted directory
    """
    print(f"Extracting {zip_path} to {extract_dir}...")
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_dir)
        print("Extraction complete")
        return Path(extract_dir)
    except zipfile.BadZipFile as e:
        print(f"Error: Invalid ZIP file: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error extracting ZIP: {e}")
        sys.exit(1)


def get_version_from_ibapi(ibapi_dir):
    """
    Extract version number from ibapi/__init__.py.
    
    Args:
        ibapi_dir: Path to ibapi directory
    
    Returns:
        str: Version string (e.g., "10.37.1") or None if not found
    """
    init_file = Path(ibapi_dir) / "__init__.py"
    if not init_file.exists():
        return None
    
    try:
        with open(init_file, 'r') as f:
            content = f.read()
            # Look for VERSION = {"major": X, "minor": Y, "micro": Z}
            version_match = re.search(
                r'VERSION\s*=\s*\{\s*"major":\s*(\d+),\s*"minor":\s*(\d+),\s*"micro":\s*(\d+)\s*\}',
                content
            )
            if version_match:
                return f"{version_match.group(1)}.{version_match.group(2)}.{version_match.group(3)}"
    except Exception as e:
        print(f"Warning: Could not read version from ibapi/__init__.py: {e}")
    
    return None


def copy_files(source_dir, dest_dir):
    """
    Copy files from source directory to destination directory.
    
    Args:
        source_dir: Source directory (IBJts/source/pythonclient/)
        dest_dir: Destination directory (project root)
    
    Returns:
        str: Version number extracted from ibapi/__init__.py
    """
    source_path = Path(source_dir)
    dest_path = Path(dest_dir)
    
    if not source_path.exists():
        print(f"Error: Source directory does not exist: {source_dir}")
        sys.exit(1)
    
    print(f"Copying files from {source_dir} to {dest_dir}...")
    
    # Extract version before copying
    source_version = get_version_from_ibapi(source_path / "ibapi")
    
    # List of files/directories to copy
    items_to_copy = [
        'ibapi',
        'setup.py',
        'MANIFEST.in',
        'pylintrc',
        'README.md',
        'tests',
        'tox.ini',
    ]
    
    copied_count = 0
    for item in items_to_copy:
        source_item = source_path / item
        dest_item = dest_path / item
        
        if source_item.exists():
            try:
                if source_item.is_dir():
                    # Remove existing directory if it exists
                    if dest_item.exists():
                        shutil.rmtree(dest_item)
                    shutil.copytree(source_item, dest_item)
                    print(f"  Copied directory: {item}/")
                else:
                    # Remove existing file if it exists
                    if dest_item.exists():
                        dest_item.unlink()
                    shutil.copy2(source_item, dest_item)
                    print(f"  Copied file: {item}")
                copied_count += 1
            except Exception as e:
                print(f"  Warning: Could not copy {item}: {e}")
        else:
            print(f"  Skipped (not found): {item}")
    
    print(f"Copy complete. Copied {copied_count} items.")
    
    # Get version from copied files
    final_version = get_version_from_ibapi(dest_path / "ibapi")
    return final_version or source_version


def get_current_version(project_root, version_type):
    """
    Get the current version from version tracking files.
    
    Args:
        project_root: Path to project root
        version_type: 'stable' or 'latest'
    
    Returns:
        str: Current version number or None
    """
    # Check for type-specific version file
    version_file = project_root / f".ibapi_{version_type}_version"
    if version_file.exists():
        try:
            with open(version_file, 'r') as f:
                data = json.load(f)
                return data.get('version')
        except Exception:
            pass
    
    # Check main version file if it matches the type
    main_version_file = project_root / ".ibapi_version"
    if main_version_file.exists():
        try:
            with open(main_version_file, 'r') as f:
                data = json.load(f)
                if data.get('type') == version_type:
                    return data.get('version')
        except Exception:
            pass
    
    # Try to get version from ibapi/__init__.py as fallback
    init_file = project_root / "ibapi" / "__init__.py"
    if init_file.exists():
        try:
            with open(init_file, 'r') as f:
                content = f.read()
                version_match = re.search(
                    r'VERSION\s*=\s*\{\s*"major":\s*(\d+),\s*"minor":\s*(\d+),\s*"micro":\s*(\d+)\s*\}',
                    content
                )
                if version_match:
                    return f"{version_match.group(1)}.{version_match.group(2)}.{version_match.group(3)}"
        except Exception:
            pass
    
    return None


def write_version_file(project_root, version_type, version_number):
    """
    Write version information to version tracking files.
    
    Args:
        project_root: Path to project root
        version_type: 'stable' or 'latest'
        version_number: Version number string
    """
    # Write to type-specific file
    version_file = project_root / f".ibapi_{version_type}_version"
    version_info = {
        'type': version_type,
        'version': version_number
    }
    
    try:
        with open(version_file, 'w') as f:
            json.dump(version_info, f, indent=2)
    except Exception as e:
        print(f"Warning: Could not write version file: {e}")


def normalize_version(version):
    """
    Normalize version string to compare properly.
    Adds .0 if only major.minor is provided.
    
    Args:
        version: Version string (e.g., "10.37" or "10.37.2")
    
    Returns:
        str: Normalized version string
    """
    if not version:
        return None
    
    parts = version.split('.')
    if len(parts) == 2:
        return f"{version}.0"
    return version


def perform_update(project_root, version_type, download_url, page_version):
    """
    Download and install the IB API files.
    
    Args:
        project_root: Path to project root
        version_type: 'stable' or 'latest'
        download_url: URL to download ZIP from
        page_version: Version number from download page
    
    Returns:
        str: Installed version number
    """
    # Create temporary directory for downloads
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        print("\n" + "="*60)
        print(f"Downloading {version_type.upper()} version:")
        print(f"  API Version: {page_version}")
        print(f"  URL: {download_url}")
        print("="*60)
        print()
        
        # Download ZIP file
        zip_filename = os.path.basename(urlparse(download_url).path)
        zip_path = temp_path / zip_filename
        download_file(download_url, zip_path)
        
        # Extract ZIP file
        extract_dir = temp_path / "extracted"
        extract_dir.mkdir()
        extract_zip(zip_path, extract_dir)
        
        # Find pythonclient directory
        extracted_contents = list(extract_dir.iterdir())
        if not extracted_contents:
            print("Error: ZIP file appears to be empty")
            sys.exit(1)
        
        # First, check if IBJts is directly in extracted directory
        ibjts_dir = None
        direct_ibjts = extract_dir / "IBJts" / "source" / "pythonclient"
        if direct_ibjts.exists():
            ibjts_dir = direct_ibjts
        else:
            # Check if IBJts is inside a subdirectory
            for item in extracted_contents:
                if item.is_dir():
                    # Look for IBJts/source/pythonclient inside this directory
                    potential_ibjts = item / "IBJts" / "source" / "pythonclient"
                    if potential_ibjts.exists():
                        ibjts_dir = potential_ibjts
                        break
        
        if not ibjts_dir:
            print("Error: Could not find IBJts/source/pythonclient directory in extracted files")
            print(f"Extracted contents: {[str(p) for p in extracted_contents]}")
            sys.exit(1)
        
        # Copy files to project root
        installed_version = copy_files(ibjts_dir, project_root)
        
        # Save version information
        if installed_version:
            write_version_file(project_root, version_type, installed_version)
            print(f"\nInstalled version: {installed_version}")
            return installed_version
        elif page_version:
            write_version_file(project_root, version_type, page_version)
            print(f"\nInstalled version (from download page): {page_version}")
            return page_version
        
        return None


def main():
    parser = argparse.ArgumentParser(
        description="Check if a new version of IB API is available and optionally update"
    )
    parser.add_argument(
        'version_type',
        choices=['stable', 'latest'],
        help="Version type to check: 'stable' or 'latest'"
    )
    parser.add_argument(
        '--update',
        action='store_true',
        help="Perform the update if a new version is available"
    )
    
    args = parser.parse_args()
    
    project_root = Path(__file__).parent.parent.parent.absolute()
    
    # Get current version
    current_version = get_current_version(project_root, args.version_type)
    current_version_normalized = normalize_version(current_version) if current_version else None
    
    # Get available version and download URL from download page
    download_url, available_version = find_download_url_and_version(args.version_type)
    available_version_normalized = normalize_version(available_version) if available_version else None
    
    # Compare versions
    has_update = False
    if available_version_normalized and current_version_normalized:
        # Parse versions to compare properly
        current_parts = [int(x) for x in current_version_normalized.split('.')]
        available_parts = [int(x) for x in available_version_normalized.split('.')]
        
        # Compare version parts
        for i in range(max(len(current_parts), len(available_parts))):
            current_part = current_parts[i] if i < len(current_parts) else 0
            available_part = available_parts[i] if i < len(available_parts) else 0
            
            if available_part > current_part:
                has_update = True
                break
            elif available_part < current_part:
                break
    elif available_version_normalized and not current_version_normalized:
        # No current version tracked, consider it an update
        has_update = True
    
    # Perform update if requested and needed
    if args.update and has_update:
        installed_version = perform_update(project_root, args.version_type, download_url, available_version)
        if installed_version:
            available_version = installed_version
    
    # Output for GitHub Actions (using GITHUB_OUTPUT file)
    output_file = os.environ.get('GITHUB_OUTPUT')
    if output_file:
        with open(output_file, 'a') as f:
            f.write(f"current_version={current_version or 'unknown'}\n")
            f.write(f"new_version={available_version or 'unknown'}\n")
            f.write(f"has_update={str(has_update).lower()}\n")
    else:
        # Fallback for local testing
        print(f"current_version={current_version or 'unknown'}")
        print(f"new_version={available_version or 'unknown'}")
        print(f"has_update={str(has_update).lower()}")
    
    # Also print for debugging
    print(f"Current {args.version_type} version: {current_version or 'unknown'}")
    print(f"Available {args.version_type} version: {available_version or 'unknown'}")
    print(f"Update needed: {has_update}")
    
    if args.update and has_update:
        print("\n" + "="*60)
        print("Update complete!")
        print(f"IB API files have been updated in: {project_root}")
        print(f"Version type: {args.version_type}")
        if available_version:
            print(f"Version number: {available_version}")
        print("="*60)
    
    sys.exit(0 if has_update else 1)


if __name__ == '__main__':
    main()
