import os
import socket
import threading
import sys
import time

class Peer:
    def __init__(self, peer_id, host, port, file_dir, known_peers = None):
        self.peer_id = peer_id
        self.host = host
        self.port = port
        self.file_dir = file_dir
        self.available_files = self.load_files()
        self.is_running = True
        if known_peers is not None:
            self.known_peers = known_peers
        else:
            self.known_peers = []
        # Initialize socket, threading, etc.

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
        for peer_addr in self.known_peers:
            if peer_addr[1] == self.port:
                continue
            for filename in self.available_files:
                # Construct offer msg: [O][Peer ID (4 bytes)][File name]
                message = b'O' + self.peer_id.to_bytes(4, 'big') +  filename.encode()
                try:
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                        s.connect(peer_addr)
                        s.sendall(message)
                    print(f"Offered file '{filename}' to {peer_addr}")
                except Exception as e:
                    print(f"Error advertising file '{filename}' to {peer_addr}: {e}")
                # Print and send to know peers
        # Readvertise every 15 secs
        threading.Timer(15, self.advertise_files).start()

    def handle_incoming_connection(self, conn):
        # Determine message type and handle accordingly.
        try:
            message_type = conn.recv(1)
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
                peer_id = int.from_bytes(peer_id_bytes, byteorder='big')
                filename = conn.recv(1024).decode()
                print(f"Received file offer from Peer {peer_id} for file: {filename}")
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
            conn.close()
        except Exception as e:
            print("Error during file tranfer: ", e)
            conn.close()


    def receive_file(self, conn, save_as="received_file"):
        # Receive file chunks and save the file.
        received_filename = os.path.join(self.file_dir, f"received_{save_as}_{int(time.time())}")
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
                    else:
                        print("Unexpected message type:", header)
                        break
            print("File received and saved as:", received_filename)
            conn.close()
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

    # Example usage: python peer.py 1234 5000
    if len(sys.argv) < 4:
        print("Usage: python peer.py <peer_id> <port> <file_dir>")
        sys.exit(1)

    peer_id = int(sys.argv[1])
    host = "localhost"
    port = int(sys.argv[2])
    file_dir = sys.argv[3]

    # FOR TESTING: Hardcode known peers
    known_peers = [("localhost", 8001), ("localhost", 8002), ("localhost", 8003), ("localhost", 8004)]

    # CREATE A PEER
    peer = Peer(peer_id, host, port, file_dir, known_peers)

    # Start server in seperate thread
    server_thread = threading.Thread(target=peer.start_server)
    server_thread.daemon = True
    server_thread.start()

    # advertise files periodically (every 15 seconds)
    peer.advertise_files()


    while True:
        command = input("Enter command(e.g., request <file> <target_host> <target_port>) or 'exit': ")
        parts = command.strip().split()
        if len(parts) == 0:
            continue
        if parts[0] == "request" and len(parts) == 4:
            file_name = parts[1]
            target_host = parts[2]
            target_port = int(parts[3])
            peer.request_file(file_name, (target_host, target_port))
        elif parts[0] == "exit":
            print("Exiting...")
            peer.is_running = False
            break
        else:
            print("Invalid command.")
            continue
