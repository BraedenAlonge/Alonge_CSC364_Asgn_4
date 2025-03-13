import os
import socket
import threading
import sys
import time


class Peer:
    def __init__(self, peer_id, host, port, file_dir, tracker_host, tracker_port):
        self.peer_id = peer_id
        self.host = host
        self.port = port
        self.file_dir = file_dir
        self.available_files = self.load_files()
        self.is_running = True
        self.known_peers = []
        # Initialize socket, threading, etc.
        self.received_files = []
        # Tracker server
        self.tracker_host = tracker_host
        self.tracker_port = tracker_port

    def register_with_tracker(self):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as soc:
                soc.connect((self.tracker_host, self.tracker_port))
                message = "JOIN " + str(self.peer_id) + " " + str(self.host) + " " + str(self.port) + "\n"
                soc.send(message.encode())
                response = soc.recv(1024).decode().strip()
                if response == "OK":
                    print("Registered with tracker.")
                else:
                    print("Tracker registration error:", response)
        except Exception as e:
            print("register_with_tracker: Tracker registration error", e)

    def update_known_peers(self):
        # Query tracker to update known peers list
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:

                s.connect((self.tracker_host, self.tracker_port))
                s.sendall("QUERY\n".encode())
                data = s.recv(4096).decode()
                peers = []
                for ln in data.splitlines():
                    if ln.startswith("PEER"):
                        parts = ln.split()
                        if len(parts) == 4:
                            peer_id = int(parts[1])
                            host = parts[2]
                            port = int(parts[3])
                            if peer_id != self.peer_id:
                                peers.append((peer_id, host, port))
                self.known_peers = peers
                print("Updated known peers from tracker server: ", peers)
        except Exception as e:
            print("update_know_peers: query error", e)

    def leave_tracker(self):
        # Tell the tracker server when we leave
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.connect((self.tracker_host, self.tracker_port))
                message = f"LEAVE {self.peer_id}\n"
                s.sendall(message.encode())
                response = s.recv(1024).decode().strip()
                if response == "OK":
                    print("Left tracker successfully.")

                else:
                    print("Tracker registration error:", response)

        except Exception as e:
            print("register_with_tracker: Tracker registration error", e)


    def load_files(self):
        # Scan file_dir and return a list or dict of files.
        files = {}
        for filename in os.listdir(self.file_dir):
            file_path = os.path.join(self.file_dir, filename)
            if os.path.isfile(file_path):
                files[filename] = file_path
        return files

    def advertise_files(self):
        # Send file offer messages to known peers.
        if not self.is_running:
            return
        # Update known peers
        self.update_known_peers()

        # Make a snapshot of the current keys to avoid the dict changing error
        file_list = list(self.available_files.keys())
        for peer_addr in self.known_peers:
            other_peer_id, other_host, other_port = peer_addr
            if  other_port == self.port:
                continue
            for filename in file_list:
                # Construct offer msg: [O][Peer ID (4 bytes)][File name]
                message = b'O' + self.peer_id.to_bytes(4, 'big') +  filename.encode()
                try:
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                        s.connect((other_host, other_port))
                        s.sendall(message)
                    print(f"Offered file '{filename}' to {(other_host, other_port)}")
                except Exception as e:
                    print(f"Error advertising file '{filename}' to {(other_host, other_port)}: {e}")
                # Print and send to know peers
        # Readvertise every 20 secs
        timer = threading.Timer(20, self.advertise_files)
        timer.daemon = True
        timer.start()
    def handle_incoming_connection(self, conn):
        # Determine message type and handle accordingly.
        try:
            message_type = conn.recv(1)
            if not message_type:
                conn.close()
                return
            if message_type == b'R':
                # Handle file request
                filename = conn.recv(1024).decode()
                print(f"Received request for file: {filename}")
                if filename in self.available_files:
                    self.send_file(self.available_files[filename], conn)
                else:
                    print("Requested file not found.")
                    conn.close()
            elif message_type == b'T':
                # If it is a transfer file, handle it (or delegate to receive_file)
                self.receive_file(conn)
            elif message_type == b'O':
                # Handle offer messages from peers
                peer_id_bytes = conn.recv(4)
                offering_peer_id = int.from_bytes(peer_id_bytes, byteorder='big')
                filename = conn.recv(1024).decode()
                print(f"Received file offer from Peer {offering_peer_id} for file: {filename}")
                # If we don't already have the file, request it
                if filename not in self.available_files:

                    # Look up offering peer's address from known peers list
                    target_peer = None
                    for p in self.known_peers:
                        if p[0] == offering_peer_id:
                            target_peer = (p[1],p[2])
                            break
                    if target_peer:
                        print(f"Requesting file {filename} from Peer "
                              f"{offering_peer_id} at {target_peer}")
                        #REQUEST SEPERATE THREAD TO NOT BLOCK HANDLER
                        threading.Thread(target=self.request_file, args=(filename, target_peer), daemon = True).start()
                    else:
                        print(f"Offering peer {offering_peer_id} not found in known peers.")

                conn.close()

            else:
                print(f"Unknown message type received: {message_type}")
                conn.close()
        except Exception as e:
            print("Error handling incoming connection", e)
            conn.close()

    def request_file(self, file_name, target_peer):
        # Create and send file request messages.
        try:
            # COMPUTE CHECKSUM

            # Target peer should be a tuple (host, port)
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as soc:
                soc.connect((target_peer[0], target_peer[1]))
                # COnstruct request
                message = b'R' + file_name.encode()
                soc.sendall(message)
                # now receive the file!
                self.receive_file(soc, save_as=file_name)
        except Exception as e:
            print("Error requesting file: ", e)


    def send_file(self, file_name, conn):
        # Open file, break it into chunks, and send with acknowledgment handling.
        try:
            checksum = self.hash(file_name)
            with open(file_name, 'rb') as f:
                chunk_number = 0
                while True:
                    chunk = f.read(1024)
                    if not chunk:
                        break
                    # Create transfer message: [T][Message]
                    message = b'T' + chunk
                    conn.sendall(message)

                    # Wait for an ack w/ timeout
                    conn.settimeout(5.0)
                    ack = conn.recv(1024)
                    # Check if it's correct format as well as if it exists
                    if not ack or ack[0:1] != b'A':
                        # Retransmit chunk
                        f.seek(chunk_number * 1024)
                        continue
                    chunk_number += 1
            print(f"File transfer complete ({chunk_number} chunks)")
            # Preface message with key 'C'
            checksum_msg = b'C' + str(checksum).encode() + b'\n'
            conn.sendall(checksum_msg)

            conn.close()
        except Exception as e:
            print("Error during file transfer: ", e)
            conn.close()

    def hash(self, file_path):
        hsh =  0
        with open(file_path, "rb") as fp:
            while True:
                data = fp.read(1024)
                if not data:
                    break
                for byte in data:
                    hsh = (hsh * 31 + int(byte)) & (2**23)
        return hsh

    def receive_file(self, conn, save_as="received_file"):
        # Receive file chunks and save the file.
        received_filename = os.path.join(self.file_dir, f"received_{save_as}")
        try:
            with open(received_filename, 'wb') as f:
                while True:
                    # Receive a chunk: expects first byte to be msg type
                    header = conn.recv(1)
                    if not header:
                        break # No more data (hopefully)
                    if header == b'T':
                        chunk = conn.recv(1024)
                        if not chunk:
                            break # uh oh
                        f.write(chunk)
                        # Send ack!!! [A][Peer ID]
                        ack = b'A' + self.peer_id.to_bytes(4, 'big')
                        conn.sendall(ack)
                    elif header == b'C':
                        data = b""
                        while True:
                            ch = conn.recv(1024)
                            if ch == b'\n': # Newline will end ch segment
                                break
                            data += ch
                        try:
                            checksum_received = int(data.decode().strip())
                        except:
                            checksum_received = None
                        print(f"Received checksum: ", checksum_received)
                        break

                    else:
                        print("Unexpected message type:", header)
                        break

            print("File received and saved as:", received_filename)
            conn.close()
            # Update available_files and received_files so we don't receive duplicates
            # Use the original file name (save_as) as the key.
            self.available_files[save_as] = received_filename

            if received_filename not in self.received_files:
                self.received_files.append(received_filename)

            calculated_checksum = self.hash(received_filename)
            if checksum_received is not None:
                if calculated_checksum == checksum_received:
                    print("File integrity check PASSED.")
                else:
                    print("File integrity check FAILED!")
                    print(f"Expected: {checksum_received}, Calculated: {calculated_checksum}")
            else:
                print("No checksum received; cannot verify integrity.")
        except Exception as e:
            print("Error receiving file:", e)
            conn.close()

    def start_server(self):
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.bind((self.host, self.port))
        server.listen()
        print(f"Peer {self.peer_id} listening on {self.host}:{self.port}")

        while self.is_running:
            try:
                conn, addr = server.accept()
                print(f"Connected by address {addr}")
                threading.Thread(target=self.handle_incoming_connection, args=(conn,)).start()
            except Exception as e:
                print("Server error:", e)
        server.close()

if __name__ == "__main__":

    # Example usage: python peer.py 1234 5000 "./Transfer-Files-Peer-4" 9000 9000
    if len(sys.argv) < 6:
        print("Usage: python peer.py <peer_id> <port> <file_dir> <tracker_host> <tracker_port>")
        sys.exit(1)

    peer_id = int(sys.argv[1])
    host = "localhost"
    port = int(sys.argv[2])
    file_dir = sys.argv[3]
    tracker_host = sys.argv[4]
    tracker_port = int(sys.argv[5])

    # CREATE A PEER
    peer = Peer(peer_id, host, port, file_dir, tracker_host, tracker_port)

    # REGISTER WITH TRACKER
    peer.register_with_tracker()

    # Start server in seperate thread
    server_thread = threading.Thread(target=peer.start_server)
    server_thread.daemon = True
    server_thread.start()

    # advertise files periodically (every 20 seconds)
    peer.advertise_files()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:

        print("Exiting...")
        peer.leave_tracker()
        peer.is_running = False
        sys.exit(0)