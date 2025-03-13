import socket
import threading

class TrackerServer:
    # well known port 9000
    def __init__(self, host='localhost', port=9000):
        self.host = host
        self.port = port
        self.peers = {}  # Mapping: peer_id -> (host, port)

        self.lock = threading.Lock()


    def handle_client(self, conn, addr):
        try:
            data = conn.recv(1024).decode().strip()
            # Join
            if data.startswith("JOIN"):
                parts = data.split()

                if len(parts) == 4:
                    peer_id = int(parts[1])
                    peer_host = parts[2]
                    peer_port = int(parts[3])
                    with self.lock:

                        self.peers[peer_id] = (peer_host, peer_port)

                    conn.sendall("OK\n".encode())
                    print(f"Peer {peer_id} joined: {(peer_host, peer_port)}")
                else:
                    conn.sendall("ERROR: Invalid JOIN format\n".encode())
            # Query
            elif data.startswith("QUERY"):
                with self.lock:
                    response = ""
                    for pid, (peer_host, peer_port) in self.peers.items():
                        response += f"PEER {pid} {peer_host} {peer_port}\n"
                conn.sendall(response.encode())
            # Leave
            elif data.startswith("LEAVE"):
                parts = data.split()
                if len(parts) == 2:
                    peer_id = int(parts[1])
                    with self.lock:
                        if peer_id in self.peers:
                            del self.peers[peer_id]
                    conn.sendall("OK\n".encode())
                    print(f"Peer {peer_id} left.")
                else:
                    conn.sendall("ERROR: Invalid LEAVE format\n".encode())
            else:
                conn.sendall("ERROR: Unknown command\n".encode())
        except Exception as e:
            print("Error handling client:", e)
        except KeyboardInterrupt:
            conn.close()
            exit(1)
        finally:
            conn.close()

    def run(self):
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.bind((self.host, self.port))
        server.listen()

        print(f"Tracker server listening on {self.host}:{self.port}")
        while True:
            try:
                conn, addr = server.accept()
                threading.Thread(target=self.handle_client, args=(conn, addr), daemon=True).start()
            except KeyboardInterrupt:
                break

if __name__ == "__main__":
    tracker = TrackerServer()
    tracker.run()