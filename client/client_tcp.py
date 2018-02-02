import os
import os.path
import socket
import sys
import time

import functools
from commands import client_commands

BUFFER_SIZE = 1024
TIMEOUT = 20

OK_STATUS = 200

global last_file_size


def wait_ok():
    while client.recv(2).decode('utf-8') != "OK":
        print("wait for OK")


def send_ok():
    client.send("OK".encode('utf-8'))


def get_data():
    return client.recv(BUFFER_SIZE).decode('utf-8')


def send_data(data):
    client.send(str(data).encode('utf-8'))


def handle_input_request(request):
    command = request.split()
    name_command = command[0].upper()

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
        send_ok()
        get_time()

    if client_commands.get(name_command) == "download":
        send_data(request)
        if not wait_for_ack(name_command):
            return
        send_ok()
        start_time = time.time()
        download(body, request)
        print("Speed: {:.2f}  MB/s".format(last_file_size * 8 / (time.time() - start_time) / 1024 / 1024))
        print("Time: {:.2f} s".format(float((time.time() - start_time)) / 1.3) )

    if client_commands.get(name_command) == "upload":
        if is_file_exist(body):
            send_data(request)
            if not wait_for_ack(name_command):
                return
            start_time = time.time()
            upload(body, request)
            print("Speed: {:.2f}  MB/s".format(last_file_size * 8 / (time.time() - start_time) / 1024 / 1024))
            print("Time: {:.2f} s".format(float((time.time() - start_time)) / 1.3))
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
        response = client.recv(BUFFER_SIZE).decode('utf-8').split(" ", 2)
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
        elif message:
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
            client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client.connect((HOST, PORT))
            client.send(request.encode('utf-8'))
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
    send_ok()
    print(get_data())


def get_time():
    print(get_data())


def download(file_name, request):
    global last_file_size

    size = int(get_data())  # 1
    last_file_size = size

    send_ok()  # 2

    wait_ok()

    send_data(0)  # 3

    data_size_recv = int(get_data())  # 4

    send_ok()  # 5

    if data_size_recv == 0:
        f = open(file_name, "wb")
    else:
        f = open(file_name, "rb+")

    while data_size_recv < size:
        try:
            data = client.recv(BUFFER_SIZE)
            f.seek(data_size_recv, 0)
            f.write(data)
            data_size_recv += len(data)
            send_data(data_size_recv)

            progress = (data_size_recv / size) * 100
            sys.stdout.write("Download progress: %d%% \r" % progress)
            sys.stdout.flush()

        except socket.error as e:
            if is_server_available(request, "download"):
                size = int(get_data())
                send_ok()
                send_data(data_size_recv)
                data_size_recv = int(get_data())
                send_ok()
                print("\n")
            else:
                f.close()
                client.close()
                os._exit(1)

        except KeyboardInterrupt:
            print("KeyboardInterrupt was handled")
            f.close()
            client.close()
            os._exit(1)

    f.close()
    print("\n" + file_name + " was downloaded")


def upload(file_name, request):
    global last_file_size

    f = open(file_name, "rb+")

    size = int(os.path.getsize(file_name))
    last_file_size = size

    send_data(size)  # 1

    wait_ok()  # 2

    send_data(0)  # 3

    data_size_recv = int(get_data())  # 4

    send_ok()

    wait_ok()  # 5

    f.seek(data_size_recv, 0)

    while data_size_recv < size:
        try:
            data_file = f.read(BUFFER_SIZE)
            client.send(data_file)
            received_data = get_data()

            progress = (float(data_size_recv) / size) * 100

            sys.stdout.write("Upload progress: %.2f%% \r" % (progress + 1))
            sys.stdout.flush()

        except socket.error as e:
            if is_server_available(request, "upload"):
                send_data(size)
                wait_ok()
                send_data(data_size_recv)
                data_size_recv = int(get_data())
                wait_ok()
                print("\n")
            else:
                f.close()
                client.close()
                os._exit(1)

        except KeyboardInterrupt:
            print("KeyboardInterrupt was handled")
            f.close()
            client.close()
            os._exit(1)

        if received_data:
            data_size_recv = int(received_data)
            f.seek(data_size_recv, 0)

    f.close()
    print("\n" + file_name + " was uploaded")


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
    print("  echo")
    print("  time")
    print("  get")
    print("  post")


is_valid_address = False

#assert len(sys.argv) == 3

#HOST = sys.argv[1]
#PORT = int(sys.argv[2])

HOST = '127.0.0.1'
PORT = 5000

show_start_message()

client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
client.setblocking(True)
client.connect((HOST, PORT))

while True:

    try:
        sys.stdout.write("> ")

        request = input()
        if check_valid_request(request):
            request = request.split()
            request[0] = request[0].upper()
            request = functools.reduce(lambda x, y: x + " " + y, request)
            handle_input_request(request)

    except KeyboardInterrupt:
        print("KeyboardInterrupt was handled")
        client.close()
        os._exit(1)
