import functools
import os
import os.path
import socket
import sys
import time

from commands import client_commands

WINDOW_SIZE = 4096

BUFFER_SIZE = 1024
TIMEOUT = 20

OK_STATUS = 200

UPLOAD_PROGRESS = 0
DOWNLOAD_PROGRESS = 0

last_file_size = 0


def get_data():
    data, address = client.recvfrom(BUFFER_SIZE)
    data = data.decode('utf-8')
    return [data, address]


def send_data(data):
    client.sendto(str(data).encode('utf-8'), server_address)


def handle_input_request(request):
    global body
    body = "Body is empty"
    command = request.split()
    name_command = command[0]

    if len(command) == 2:
        body = command[1]

    if client_commands.get(name_command) == "echo":
        send_data(request)
        if not wait_for_ack(name_command):
            return
        echo()

    if client_commands.get(name_command) == "time":
        send_data(request)
        if not wait_for_ack(name_command):
            return
        get_time()

    if client_commands.get(name_command) == "download":
        send_data(request)
        if not wait_for_ack(name_command):
            return
        start_time = time.time()
        download(body)
        print("Speed: {:.2f} MB/s".format(last_file_size / (time.time() - start_time) / 1024 / 1024 * 8))

    if client_commands.get(name_command) == "upload":
        if is_file_exist(body):
            send_data(request)
            if not wait_for_ack(name_command):
                return
            start_time = time.time()
            upload(body)
            print("Speed: {:.2f} MB/s".format(last_file_size / (time.time() - start_time) / 1024 / 1024 * 8))
        else:
            show_error_message("No such file exists")

    if client_commands.get(name_command) == "exit":
        send_data(request)
        if not wait_for_ack(name_command):
            return
        client.close()
        os._exit(1)


def wait_for_ack(command_to_compare):
    while True:
        response = get_data()[0].split(" ", 2)

        if not response:
            return False

        sent_request = response[0]
        status = response[1]

        if len(response) > 2:
            message = response[2]
        else:
            message = None

        if command_to_compare == sent_request and int(status) == OK_STATUS:
            return True
        elif (message):
            print(message)
            return False
        else:
            return False


def is_server_available(request, command):
    global client

    client.close()

    i = TIMEOUT

    while i > 0:
        try:
            client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            client.connect(server_address)
            client.sendto(request.encode('utf-8'), server_address)
            wait_for_ack(command)
            return True

        except socket.error as er:
            sys.stdout.write("Waiting for a server: %d seconds \r" % i)
            sys.stdout.flush()

        i -= 1
        time.sleep(1)

    sys.stdout.flush()
    print("\nServer was disconnected")
    sys.stdout.flush()
    return False


def is_file_exist(file_name):
    return os.path.exists(file_name)


def echo():
    print(get_data()[0])


def get_time():
    print(get_data()[0])


def handle_disconnect():
    print("wait server")
    time.sleep(1)


def download(file_name):
    global WINDOW_SIZE, last_file_size

    send_data(WINDOW_SIZE)

    WINDOW_SIZE = int(get_data()[0])
    server_window = WINDOW_SIZE

    size = int(get_data()[0])
    last_file_size = size

    send_data(DOWNLOAD_PROGRESS)

    data_size_recv = int(get_data()[0])

    if data_size_recv == 0:
        f = open(file_name, "wb")
    else:
        f = open(file_name, "rb+")

    current_pos = data_size_recv

    i = 0
    while True:
        try:
            data = client.recvfrom(BUFFER_SIZE)[0]
            if data:
                if data == b'EOF':
                    break
                else:
                    i += 1
                    f.seek(current_pos, 0)
                    f.write(data)
                    current_pos += len(data)
                    server_window -= len(data)
                    if server_window == 0:
                        server_window = WINDOW_SIZE
                        send_data(current_pos)
            else:
                print("Server disconnected")
                return

            progress = (current_pos / size) * 100
            sys.stdout.flush()
            sys.stdout.write("Download progress: %d%% \r" % progress)

        except KeyboardInterrupt:
            print("KeyboardInterrupt was handled")
            send_data("ERROR")
            f.close()
            client.close()
            os._exit(1)

    f.close()
    print("\n" + file_name + " was downloaded")


def upload(file_name):
    global WINDOW_SIZE, last_file_size

    f = open(file_name, "rb+")

    size = int(os.path.getsize(file_name))
    last_file_size = size

    send_data(WINDOW_SIZE)  # 1

    WINDOW_SIZE = int(get_data()[0])  # 2
    server_window = WINDOW_SIZE

    send_data(size)  # 3

    send_data(0)  # 4

    data_size_recv = int(get_data()[0])  # 5

    current_pos = data_size_recv

    f.seek(current_pos, 0)

    while (1):
        try:
            if current_pos >= size:
                client.sendto(b"EOF", server_address)
                break
            else:
                data_file = f.read(BUFFER_SIZE)
                client.sendto(data_file, server_address)
                current_pos += BUFFER_SIZE
                f.seek(current_pos)

            server_window -= BUFFER_SIZE
            if server_window == 0:
                server_window = WINDOW_SIZE
                send_data(current_pos)

            progress = (current_pos / size) * 100

            sys.stdout.write("Upload progress: %d%% \r" % progress)
            sys.stdout.flush()

        except KeyboardInterrupt:
            print("KeyboardInterrupt handled")
            client.sendto(b"ERROR", server_address)
            f.close()
            client.close()
            os._exit(1)

    f.close()
    print("\n" + file_name + " was uploaded")


def exit():
    pass


def check_valid_request(request):
    command = request.split()
    if len(command) == 0:
        return False
    else:
        return True


def show_status():
    pass


def show_error_message(error):
    print(error)


def show_start_message():
    print(" Usage:")
    print("  time")
    print("  echo")
    print("  get")
    print("  post")


#assert len(sys.argv) == 3
#HOST = sys.argv[1]
#PORT = int(sys.argv[2])

HOST = '127.0.0.1'
PORT = 5000

client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
is_valid_address = False
server_address = (HOST, PORT)

show_start_message()


while True:
    sys.stdout.write("> ")
    request = input()

    if not request:
        continue
    request = request.split()
    request[0] = request[0].upper()
    request = functools.reduce(lambda x, y: x + " " + y, request)

    handle_input_request(request)
