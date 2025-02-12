import tkinter as tk
from tkinter import scrolledtext, messagebox, simpledialog
import threading
import socket
import sys
import struct
import ast 

PORT = 56789 
MSGLEN = 409600               

CMD_LOGIN      = 1
CMD_CREATE     = 2
CMD_SEND       = 3
CMD_READ       = 4
CMD_DELETE_MSG = 5
CMD_VIEW_CONV  = 6
CMD_DELETE     = 7 
CMD_LOGOFF     = 8
CMD_CLOSE      = 9
CMD_CHAT       = 10
CMD_LIST       = 11

HEADER_FORMAT = "!BH" 
HEADER_SIZE = struct.calcsize(HEADER_FORMAT) 

def encode_message(cmd, payload_bytes):
    # Pack the command and length of the payload into a header
    header = struct.pack(HEADER_FORMAT, cmd, len(payload_bytes))
    # Return header concatenated with payload
    return header + payload_bytes

def decode_message(sock):
    # Read the header first
    header = b""
    while len(header) < HEADER_SIZE:
        chunk = sock.recv(HEADER_SIZE - len(header))
        if not chunk:
            # Connection closed unexpectedly
            raise Exception("Connection closed while reading header")
        header += chunk
    # Unpack header to get command and payload length
    cmd, payload_len = struct.unpack(HEADER_FORMAT, header)
    payload = b""
    # Read the payload based on length specified in header
    while len(payload) < payload_len:
        chunk = sock.recv(payload_len - len(payload))
        if not chunk:
            raise Exception("Connection closed while reading payload")
        payload += chunk
    return cmd, payload

def pack_short_string(s):
    # Convert string to bytes using UTF-8 encoding
    b = s.encode('utf-8')
    # Check that the string is not too long to pack in 1 byte length
    if len(b) > 255:
        raise ValueError("String too long for short string (exceeds 255 bytes).")
    # Pack length (1 byte) and then the actual string bytes
    return struct.pack("!B", len(b)) + b

def unpack_short_string(data, offset):
    # Unpack the length of the short string (1 byte)
    length = struct.unpack_from("!B", data, offset)[0]
    offset += 1
    # Extract the string bytes based on the length and decode to UTF-8
    s = data[offset:offset+length].decode('utf-8')
    offset += length
    return s, offset

def pack_long_string(s):
    # Convert string to bytes using UTF-8 encoding
    b = s.encode('utf-8')
    # Ensure string length fits within 2 bytes length (max 65535)
    if len(b) > 65535:
        raise ValueError("String too long for long string (exceeds 65535 bytes).")
    # Pack length (2 bytes) and then the string bytes
    return struct.pack("!H", len(b)) + b

def unpack_long_string(data, offset):
    # Unpack the length of the long string (2 bytes)
    length = struct.unpack_from("!H", data, offset)[0]
    offset += 2
    # Extract and decode the string
    s = data[offset:offset+length].decode('utf-8')
    offset += length
    return s, offset

def decode_response(cmd, payload):
    # For commands that expect a short response
    if cmd in (CMD_LOGIN, CMD_CREATE, CMD_SEND, CMD_DELETE_MSG, CMD_LOGOFF, CMD_DELETE, CMD_CLOSE):
        try:
            # Try unpacking as a short string first
            resp, _ = unpack_short_string(payload, 0)
        except Exception:
            # If that fails, try unpacking as a long string
            resp, _ = unpack_long_string(payload, 0)
        return resp
    elif cmd in (CMD_LIST, CMD_VIEW_CONV):
        # For listing users or viewing conversations, unpack as a long string
        resp, _ = unpack_long_string(payload, 0)
        return resp
    elif cmd == CMD_READ:
        # For reading messages, check if payload starts with a marker (first byte = 0)
        if payload[0] == 0:
            marker_length = struct.unpack_from("!H", payload, 0)[0]
            if len(payload) == 2 + marker_length:
                marker, _ = unpack_long_string(payload, 0)
                # Recognize special markers for end or absence of messages
                if marker in ("END_OF_MESSAGES", "NO_MESSAGES"):
                    return ""
                else:
                    return marker
        # Otherwise, unpack a sender and a long message
        sender, offset = unpack_short_string(payload, 0)
        message, _ = unpack_long_string(payload, offset)
        return {"sender": sender, "message": message}
    elif cmd == CMD_CHAT:
        try:
            # For chat messages, try unpacking sender and message
            sender, offset = unpack_short_string(payload, 0)
            message, _ = unpack_long_string(payload, offset)
            return {"sender": sender, "message": message}
        except Exception:
            # Fallback: decode as plain UTF-8 text
            return payload.decode('utf-8', errors='replace')
    else:
        # For any unknown command, decode the payload as UTF-8
        return payload.decode('utf-8', errors='replace')

class ChatClient:
    def __init__(self, server_host, server_port):
        # Save server connection info
        self.server_host = server_host
        self.server_port = server_port
        # Create a new TCP socket
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # Connect to the chat server
        self.sock.connect((server_host, server_port))
        self.username = None
        self.running = True

    def send_message(self, cmd, data):
        # Build payloads based on the command type
        if cmd in (CMD_LOGIN, CMD_CREATE):
            username = data.get("from", "")
            password = data.get("password", "")
            # For login or account creation, pack username and password as short strings
            payload = pack_short_string(username) + pack_short_string(password)
        elif cmd == CMD_SEND:
            sender = data.get("from", "")
            recipient = data.get("to", "")
            message = data.get("body", "")
            # For sending messages, pack sender, recipient and message (as a long string)
            payload = pack_short_string(sender) + pack_short_string(recipient) + pack_long_string(message)
        elif cmd == CMD_LIST:
            wildcard = data.get("body", "*")
            # Use a wildcard to list matching accounts; pack as a short string
            payload = pack_short_string(wildcard)
        elif cmd == CMD_READ:
            username = data.get("from", "")
            try:
                # Limit indicates the number of messages to retrieve
                limit = int(data.get("body", "0"))
            except:
                limit = 0
            # Pack username and limit (1 byte)
            payload = pack_short_string(username) + struct.pack("!B", limit)
        elif cmd == CMD_DELETE_MSG:
            username = data.get("from", "")
            indices_str = data.get("body", "")
            indices = []
            # Parse comma-separated message indices to delete
            for part in indices_str.split(","):
                part = part.strip()
                if part.isdigit():
                    indices.append(int(part))
            count = len(indices)
            payload = pack_short_string(username) + struct.pack("!B", count)
            # Append each index as a byte
            for idx in indices:
                payload += struct.pack("!B", idx)
        elif cmd == CMD_VIEW_CONV:
            username = data.get("from", "")
            other = data.get("to", "")
            # Pack usernames to view conversation between two users
            payload = pack_short_string(username) + pack_short_string(other)
        elif cmd in (CMD_DELETE, CMD_LOGOFF, CMD_CLOSE):
            username = data.get("from", "")
            # For account deletion, logoff, or closing, only the username is needed
            payload = pack_short_string(username)
        else:
            payload = b""
        # Encode the complete message (header + payload) and send it
        msg = encode_message(cmd, payload)
        self.sock.sendall(msg)

    def close(self):
        # Stop the receive loop and close the socket connection
        self.running = False
        self.sock.close()

    def receive_loop(self, callback):
        # Continuously listen for incoming messages from the server
        while self.running:
            try:
                cmd, payload = decode_message(self.sock)
            except Exception as e:
                # Print error to stderr if connection is lost or an error occurs
                print("Error receiving message:", e, file=sys.stderr)
                break
            # Decode the received payload and wrap it in a dictionary
            data = {"cmd": cmd, "body": decode_response(cmd, payload)}
            # Use the provided callback to handle the message (usually updating the UI)
            callback(data)
        # Ensure the socket is closed when loop ends
        self.close()

class ChatGUI:
    def __init__(self, master):
        # Initialize the main window and set its title
        self.master = master
        self.master.title("Custom Protocol Chat Client")
        self.client = None           # Will hold the ChatClient instance
        self.user_list = []          # List of users available on the server
        self.username = ""           # Current logged-in user's name

        # Create frames for different parts of the interface
        self.login_frame = tk.Frame(master)
        self.chat_frame = tk.Frame(master)
        self.command_frame = tk.Frame(master)

        # Setup each frame with UI components
        self.setup_login_frame()
        self.setup_chat_frame()
        self.setup_command_frame()

        # Start by displaying the login frame
        self.login_frame.pack()

    def setup_login_frame(self):
        # Create and position labels and entry fields for server IP, username, and password
        tk.Label(self.login_frame, text="Server IP:").grid(row=0, column=0, sticky="e")
        self.server_ip_entry = tk.Entry(self.login_frame)
        self.server_ip_entry.insert(0, "127.0.0.1")  # Default IP value
        self.server_ip_entry.grid(row=0, column=1, padx=5, pady=5)

        tk.Label(self.login_frame, text="Username:").grid(row=1, column=0, sticky="e")
        self.username_entry = tk.Entry(self.login_frame)
        self.username_entry.grid(row=1, column=1, padx=5, pady=5)

        tk.Label(self.login_frame, text="Password:").grid(row=2, column=0, sticky="e")
        self.password_entry = tk.Entry(self.login_frame, show="*")
        self.password_entry.grid(row=2, column=1, padx=5, pady=5)

        # Buttons to login, create an account, or exit the application
        self.login_button = tk.Button(self.login_frame, text="Login", command=self.login)
        self.login_button.grid(row=3, column=0, padx=5, pady=5)

        self.create_button = tk.Button(self.login_frame, text="Create Account", command=self.create_account)
        self.create_button.grid(row=3, column=1, padx=5, pady=5)

        self.exit_button = tk.Button(self.login_frame, text="Exit", command=self.close)
        self.exit_button.grid(row=4, column=0, columnspan=2, padx=5, pady=5)

    def setup_chat_frame(self):
        # Create a read-only text area for displaying chat messages
        self.chat_display = scrolledtext.ScrolledText(self.chat_frame, state="disabled", width=60, height=20)
        self.chat_display.grid(row=0, column=0, columnspan=2, padx=10, pady=10)

        # Dropdown menu for selecting the message recipient
        tk.Label(self.chat_frame, text="Recipient:").grid(row=1, column=0, sticky="e", padx=5)
        self.recipient_var = tk.StringVar()
        self.recipient_var.set("All")
        self.recipient_menu = tk.OptionMenu(self.chat_frame, self.recipient_var, "All")
        self.recipient_menu.grid(row=1, column=1, sticky="w", padx=5, pady=5)

        # Entry field for typing chat messages
        tk.Label(self.chat_frame, text="Message:").grid(row=2, column=0, sticky="e", padx=5)
        self.msg_entry = tk.Entry(self.chat_frame, width=40)
        self.msg_entry.grid(row=2, column=1, sticky="w", padx=5, pady=5)
        # Bind the Enter key to sending a chat message
        self.msg_entry.bind("<Return>", lambda event: self.send_chat())

        # Button to send a chat message
        self.send_button = tk.Button(self.chat_frame, text="Send", command=self.send_chat)
        self.send_button.grid(row=3, column=1, sticky="w", padx=5, pady=5)

    def setup_command_frame(self):
        # Button to refresh the list of available users
        self.list_button = tk.Button(self.command_frame, text="Refresh Users", command=self.refresh_users)
        self.list_button.grid(row=0, column=0, padx=5, pady=5)

        # Button to delete selected messages
        self.delete_msg_button = tk.Button(self.command_frame, text="Delete Messages", command=self.delete_messages)
        self.delete_msg_button.grid(row=0, column=1, padx=5, pady=5)

        # Dropdown and button to view conversation with a specific user
        tk.Label(self.command_frame, text="View Conversation:").grid(row=1, column=0, padx=5, pady=5)
        self.view_conv_var = tk.StringVar()
        self.view_conv_var.set("Select User")
        self.view_conv_menu = tk.OptionMenu(self.command_frame, self.view_conv_var, "Select User")
        self.view_conv_menu.grid(row=1, column=1, padx=5, pady=5)

        self.view_conv_button = tk.Button(self.command_frame, text="View", command=self.view_conversation)
        self.view_conv_button.grid(row=1, column=2, padx=5, pady=5)

        # Button to delete the user account
        self.delete_acc_button = tk.Button(self.command_frame, text="Delete Account", command=self.delete_account)
        self.delete_acc_button.grid(row=0, column=2, padx=5, pady=5)

        # Button to log off from the current session
        self.logoff_button = tk.Button(self.command_frame, text="Log Off", command=self.logoff)
        self.logoff_button.grid(row=0, column=3, padx=5, pady=5)

        # Button to close the application
        self.close_button = tk.Button(self.command_frame, text="Close", command=self.close)
        self.close_button.grid(row=0, column=4, padx=5, pady=5)

        # Another button to refresh users (duplicate functionality)
        self.refresh_button = tk.Button(self.command_frame, text="Refresh Users", command=self.refresh_users)
        self.refresh_button.grid(row=1, column=3, padx=5, pady=5)

        # Button to read unread messages
        self.read_button = tk.Button(self.command_frame, text="Read Unread Messages", command=self.read_messages)
        self.read_button.grid(row=1, column=4, padx=5, pady=5)

    def update_recipient_menu(self):
        # Update the recipient menu with the latest user list
        menu = self.recipient_menu["menu"]
        menu.delete(0, "end")
        current = self.username if self.username else self.username_entry.get().strip()
        # Exclude the current user from the recipient list and include "All"
        options = ["All"] + sorted([user for user in self.user_list if user != current])
        for option in options:
            menu.add_command(label=option, command=lambda value=option: self.recipient_var.set(value))
        # Set default recipient option
        self.recipient_var.set(options[0] if options else "All")

    def update_view_conv_menu(self):
        # Update the view conversation menu with the latest user list
        menu = self.view_conv_menu["menu"]
        menu.delete(0, "end")
        current = self.username if self.username else self.username_entry.get().strip()
        options = ["Select User"] + sorted([user for user in self.user_list if user != current])
        for option in options:
            menu.add_command(label=option, command=lambda value=option: self.view_conv_var.set(value))
        self.view_conv_var.set(options[0] if options else "Select User")

    def refresh_users(self):
        # Send a request to the server to list all user accounts
        if self.client:
            list_msg = {"from": self.username, "body": "*"}
            self.client.send_message(CMD_LIST, list_msg)

    def login(self):
        # Retrieve server IP, username, and password from the login fields
        server_ip = self.server_ip_entry.get().strip()
        username = self.username_entry.get().strip()
        password = self.password_entry.get().strip()
        # Ensure all fields are filled in
        if not server_ip or not username or not password:
            messagebox.showerror("Error", "Please fill in all fields.")
            return
        try:
            # Create a new chat client connection
            self.client = ChatClient(server_ip, PORT)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to connect to server: {e}")
            return
        self.username = username
        # Create and send a login message using CMD_LOGIN
        login_msg = {"from": username, "password": password}
        self.client.send_message(CMD_LOGIN, login_msg)
        # Start a separate thread to handle incoming messages
        threading.Thread(target=self.client.receive_loop, args=(self.handle_message,), daemon=True).start()

    def create_account(self):
        # Retrieve input fields for account creation
        server_ip = self.server_ip_entry.get().strip()
        username = self.username_entry.get().strip()
        password = self.password_entry.get().strip()
        if not server_ip or not username or not password:
            messagebox.showerror("Error", "Please fill in all fields.")
            return
        try:
            self.client = ChatClient(server_ip, PORT)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to connect to server: {e}")
            return
        self.username = username
        # Send a create account request using CMD_CREATE
        create_msg = {"from": username, "password": password}
        self.client.send_message(CMD_CREATE, create_msg)
        threading.Thread(target=self.client.receive_loop, args=(self.handle_message,), daemon=True).start()

    def send_chat(self):
        # Retrieve the message from the input field
        message = self.msg_entry.get().strip()
        if not message:
            return
        # Get the selected recipient from the dropdown
        recipient = self.recipient_var.get()
        chat_msg = {"from": self.username, "to": recipient, "body": message}
        # Send the chat message using CMD_SEND
        self.client.send_message(CMD_SEND, chat_msg)
        # Clear the message entry field after sending
        self.msg_entry.delete(0, tk.END)

    def list_accounts(self):
        # Open a dialog to input a wildcard for account listing
        wildcard = simpledialog.askstring("List Accounts", "Enter wildcard (leave blank for all):", parent=self.master)
        if wildcard is None:
            return
        list_msg = {"from": self.username, "body": wildcard}
        self.client.send_message(CMD_LIST, list_msg)

    def delete_messages(self):
        # Ask the user which message IDs to delete (comma separated)
        indices = simpledialog.askstring("Delete Messages", "Enter message IDs to delete (comma separated):", parent=self.master)
        if indices is None:
            return
        del_msg = {"from": self.username, "body": indices}
        self.client.send_message(CMD_DELETE_MSG, del_msg)

    def view_conversation(self):
        # Get the selected user from the view conversation dropdown
        other_user = self.view_conv_var.get()
        if other_user == "Select User":
            messagebox.showerror("Error", "Please select a valid user.")
            return
        view_msg = {"from": self.username, "to": other_user}
        self.client.send_message(CMD_VIEW_CONV, view_msg)

    def read_messages(self):
        # Ask the user for the number of unread messages to retrieve
        limit_str = simpledialog.askstring("Read Unread Messages", "Enter number of unread messages to view (0 for all):", parent=self.master)
        if limit_str is None:
            return
        try:
            limit = int(limit_str)
        except ValueError:
            messagebox.showerror("Error", "Please enter a valid number.")
            return
        read_msg = {"from": self.username, "body": str(limit)}
        self.client.send_message(CMD_READ, read_msg)

    def delete_account(self):
        # Confirm with the user if they really want to delete their account
        confirm = messagebox.askyesno("Delete Account", "Are you sure you want to delete your account? This cannot be undone.", parent=self.master)
        if confirm:
            del_msg = {"from": self.username}
            self.client.send_message(CMD_DELETE, del_msg)

    def logoff(self):
        # Log off from the current session by sending CMD_LOGOFF
        if self.client:
            logoff_msg = {"from": self.username}
            self.client.send_message(CMD_LOGOFF, logoff_msg)
            self.client.close()
            self.client = None
        # Reset the UI: hide chat and command frames, show login frame
        self.chat_frame.pack_forget()
        self.command_frame.pack_forget()
        self.chat_display.configure(state="normal")
        self.chat_display.delete("1.0", tk.END)
        self.chat_display.configure(state="disabled")
        self.login_frame.pack()
        self.username_entry.delete(0, tk.END)
        self.password_entry.delete(0, tk.END)
        self.username = ""

    def close(self):
        # If connected, send a CMD_CLOSE message before closing the application
        if self.client:
            close_msg = {"from": self.username}
            self.client.send_message(CMD_CLOSE, close_msg)
            self.client.close()
            self.client = None
        self.master.destroy()

    def handle_message(self, msg):
        # This method is called by the ChatClient thread when a message is received
        cmd = msg.get("cmd", "")
        body = msg.get("body", "")
        if cmd == CMD_LIST:
            # When a list of accounts is received, update the UI and user list
            self.append_text("Matching accounts:\n" + body)
            accounts = [x.strip() for x in body.split(",") if x.strip()]
            self.user_list = accounts
            self.update_recipient_menu()
            self.update_view_conv_menu()
        elif cmd == CMD_LOGIN:
            # On successful login, switch to chat view and clear the chat display
            self.chat_display.configure(state="normal")
            self.chat_display.delete("1.0", tk.END)
            self.chat_display.configure(state="disabled")
            self.login_frame.pack_forget()
            self.chat_frame.pack()
            self.command_frame.pack()
            self.append_text(body)
            self.refresh_users()
        elif cmd == CMD_CREATE:
            # Inform the user that the account was created
            messagebox.showinfo("Account Created", body)
        elif cmd == CMD_READ:
            # Display unread messages
            if isinstance(body, dict):
                self.append_text(f"Unread Message: {body['sender']}: {body['message']}")
            elif body == "":
                # If no unread messages, do nothing
                pass
            else:
                self.append_text("Unread Message: " + str(body))
        elif cmd == CMD_CHAT:
            # Display chat messages in the chat display
            if isinstance(body, dict):
                sender = body.get("sender", "Unknown")
                message_text = body.get("message", "")
                self.append_text(f"{sender}: {message_text}")
            else:
                self.append_text(body)
        elif cmd == CMD_SEND:
            self.append_text(body)
        elif cmd == CMD_DELETE_MSG:
            self.append_text(body)
        elif cmd == CMD_VIEW_CONV:
            # Try to pretty-print the conversation
            try:
                conv = ast.literal_eval(body)
                formatted = "Conversation:\n"
                for msg_item in conv:
                    timestamp = msg_item.get("timestamp", "")
                    sender = msg_item.get("sender", "")
                    message_text = msg_item.get("message", "")
                    formatted += f"[{timestamp}] {sender}: {message_text}\n"
                self.append_text(formatted)
            except Exception as e:
                # If formatting fails, display the raw conversation text
                self.append_text("Conversation:\n" + body)
        elif cmd == CMD_DELETE:
            # After account deletion, reset to the login view
            self.append_text(body)
            self.username_entry.delete(0, tk.END)
            self.login_frame.pack()
            self.chat_frame.pack_forget()
            self.command_frame.pack_forget()
            self.username = ""
        elif cmd == CMD_LOGOFF:
            self.append_text(body)
        else:
            # For any unrecognized command, display its number and body
            self.append_text(f"{cmd}: {body}")

    def append_text(self, text):
        # Thread-safe method to append text to the chat display area
        def update():
            self.chat_display.configure(state="normal")
            self.chat_display.insert(tk.END, text + "\n")
            self.chat_display.configure(state="disabled")
            self.chat_display.see(tk.END)
        self.master.after(0, update)

if __name__ == "__main__":
    # Create the main Tkinter window and start the GUI
    root = tk.Tk()
    gui = ChatGUI(root)
    root.mainloop()
