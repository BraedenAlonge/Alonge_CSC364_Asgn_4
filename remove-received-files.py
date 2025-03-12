import os

""" Remove received files. Simply run the program with no args"""

def main():
    directories = [
        "Transfer-Files-Peer-1", "Transfer-Files-Peer-2",
        "Transfer-Files-Peer-3","Transfer-Files-Peer-4"]

    # Loop through each directory
    for directory in directories:
        if not os.path.isdir(directory):
            continue
        # List all files in dir
        for filename in os.listdir(directory):
            # Check if "received_" is in the filename
            if "received_" in filename:
                file_path = os.path.join(directory, filename)
                # Verify it's a file before removing
                if os.path.isfile(file_path):
                    os.remove(file_path)



if __name__ == '__main__':
    main()