"""
Simple text search across all .txt files in a folder.

Usage:
    1. Set FOLDER_PATH below to the folder containing your .txt files.
    2. Run:  python search_text.py
    3. Type the text you want to search for and press Enter.
    4. It prints every file + line number where the text appears.
    5. Type 'quit' to exit.
"""

import os

# ----------------------------------------------------------------------
# CONFIG: change this to the folder that holds your .txt files.
# Examples:
#   FOLDER_PATH = r"C:\Users\Harsh\Documents\my_texts"   (Windows)
#   FOLDER_PATH = "."   (the same folder this script is in)
# ----------------------------------------------------------------------
FOLDER_PATH = "."

# Case-insensitive search by default. Set to False for exact-case matching.
IGNORE_CASE = True


def search(term, folder):
    if not os.path.isdir(folder):
        print(f"  ! Folder not found: {folder}")
        return

    needle = term.lower() if IGNORE_CASE else term
    total_matches = 0
    files_searched = 0

    for filename in sorted(os.listdir(folder)):
        if not filename.lower().endswith(".txt"):
            continue

        files_searched += 1
        filepath = os.path.join(folder, filename)

        try:
            # errors="ignore" so a stray odd character won't crash the search
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                for line_number, line in enumerate(f, start=1):
                    haystack = line.lower() if IGNORE_CASE else line
                    if needle in haystack:
                        total_matches += 1
                        print(f"  {filename}  (line {line_number}): {line.strip()}")
        except Exception as e:
            print(f"  ! Could not read {filename}: {e}")

    print(f"\n  Searched {files_searched} file(s). Found {total_matches} match(es).\n")


def main():
    print("=" * 60)
    print("  Text search across .txt files")
    print(f"  Folder: {os.path.abspath(FOLDER_PATH)}")
    print("  Type your search text, or 'quit' to exit.")
    print("=" * 60)

    while True:
        term = input("\nSearch for: ").strip()
        if term.lower() in ("quit", "exit", "q"):
            print("Bye.")
            break
        if not term:
            print("  (empty input — type something to search)")
            continue
        print()
        search(term, FOLDER_PATH)


if __name__ == "__main__":
    main()