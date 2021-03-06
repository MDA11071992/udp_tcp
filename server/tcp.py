import os
import os.path
import socket
import sys
from datetime import datetime
from time import sleep
from multiprocessing import Process, Manager

from commands import server_commands, client_commands, help_list

IP = '127.0.0.1'
PORT = 5000

BUFFER_SIZE = 1024
WINDOW_SIZE = 4096

TIMEOUT = 20

OK_STATUS = 200
SERVER_ERROR = 500


def send_status_and_message(client, request, status, message):
    message = str("" + request + " " + str(status) + " " + message)
    client.send(message.encode('utf-8'))


def send_status(client, request, status):
    message = str("" + request + " " + str(status))
    client.send(message.encode('utf-8'))


def is_file_exist(file_name):
    return os.path.exists(file_name)


def handle_client(client):
    if not client["is_closed"]:
        request = client['socket'].recv(BUFFER_SIZE).decode('utf-8')
        request = request.strip()
        if request != '':
            print("[*] Received: %s" % request)
            handle_client_request(client, request)


def echo(client, body):
    send_data(client, body)


def send_time(client):
    server_time = "Server time: " + str(datetime.now())[:19]
    send_data(client, server_time)


def exit_client(client):
    global inputs

    sys.exit(0)


def handle_client_request(client, request):
    global body
    body = "Body is empty"
    command = request.split()
    name_command = command[0]
    if len(command) == 2:
        body = command[1]

    if client_commands.get(name_command) == "download":
        if is_file_exist(body):
            send_status(client['socket'], name_command, OK_STATUS)
            wait_ok(client)
            download(client, body)
        else:
            no_file = "File: " + body + " is not exist."
            send_status_and_message(client['socket'], name_command, SERVER_ERROR, "No such file")

    elif client_commands.get(name_command) == "upload":
        send_status(client['socket'], name_command, OK_STATUS)
        upload(client, body)

    elif client_commands.get(name_command) == "echo":
        send_status(client['socket'], name_command, OK_STATUS)
        wait_ok(client)
        echo(client, body)

    elif client_commands.get(name_command) == "time":
        send_status(client['socket'], name_command, OK_STATUS)
        wait_ok(client)
        send_time(client)

    elif client_commands.get(name_command) == "exit":
        send_status(client['socket'], name_command, OK_STATUS)
        exit_client(client)

    elif client_commands.get(name_command) == "delete":
        if is_file_exist(body):
            send_status(client['socket'], name_command, OK_STATUS)
            delete(client, body)
        else:
            no_file = "File: " + body + " is not exist."
            send_status_and_message(client['socket'], name_command, SERVER_ERROR, "No such file")

    else:
        send_status_and_message(client['socket'], name_command, SERVER_ERROR, "Unknown command")


def delete(client, file_name):
    pass


def search_by_ip(xs, ip):
    found_client = [element for element in xs if element['ip'] == ip]
    return found_client[0] if len(found_client) > 0 else False


def search_by_socket(xs, socket):
    found_client = [element for element in xs if element['socket'] == socket]
    return found_client[0] if len(found_client) > 0 else False


def save_to_waiting_clients(ip, command, file_name, progress):
    waiting_clients.append(
        {
            'ip': ip,
            'command': command,
            'file_name': file_name,
            'progress': progress
        })


def handle_disconnect(client, command, file_name, progress):
    save_to_waiting_clients(client['ip'], command, file_name, progress)
    clients_pool.remove(client)
    inputs.remove(client['socket'])
    client['socket'].close()

    sys.stdout.flush()
    print("\nClient was disconnected")
    sys.stdout.flush()


def wait_ok(client):
    while client['socket'].recv(2).decode('utf-8') != "OK":
        print("wait for OK")


def send_ok(client):
    client['socket'].send("OK".encode('utf-8'))


def get_data(client):
    return client['socket'].recv(BUFFER_SIZE).decode('utf-8')


def send_data(client, data):
    client['socket'].send(str(data).encode('utf-8'))
    #server_udp.sendto(str(data).encode('utf-8'), client)


def download(client, file_name):
    global received_data
    f = open(file_name, "rb+")

    size = int(os.path.getsize(file_name))

    send_data(client, size)  # 1

    wait_ok(client)  # 2

    waiting_client = search_by_ip(waiting_clients, client['ip'])
    if len(waiting_clients) > 0 and waiting_client != False:
        waiting_clients.remove(waiting_client)

    send_ok(client)

    data_size_recv = int(get_data(client))  # 3

    if waiting_client:
        if waiting_client['file_name'] == file_name and waiting_client['command'] == 'download':
            data_size_recv = int(waiting_client['progress'])
            send_data(client, data_size_recv)
    else:
        send_data(client, data_size_recv)  # 4

    wait_ok(client)  # 5

    f.seek(data_size_recv, 0)

    while data_size_recv < size:
        try:
            data_file = f.read(BUFFER_SIZE)
            client['socket'].sendall(data_file)
            received_data = get_data(client)

        except socket.error as e:
            print(e.strerror)
            f.close()
            handle_disconnect(client, "download", file_name, data_size_recv)
            client['is_closed'] = True
            return

        except KeyboardInterrupt:
            server_tcp.close()
            client.socket.close()
            os._exit(1)

        if received_data:
            if str(received_data).isdigit():
                data_size_recv = int(received_data)
                f.seek(data_size_recv)

    f.close()


def upload(client, file_name):
    size = int(get_data(client))  # 1

    send_ok(client)  # 2
    data_size_recv = get_data(client)  # 3
    if data_size_recv:
        data_size_recv = int(data_size_recv)

    waiting_client = search_by_ip(waiting_clients, client['ip'])
    if len(waiting_clients) > 0 and waiting_client != False:
        waiting_clients.remove(waiting_client)

    if waiting_client:
        if waiting_client['file_name'] == file_name and waiting_client['command'] == 'upload':
            data_size_recv = int(waiting_client['progress'])
            send_data(client, data_size_recv)
    else:
        send_data(client, data_size_recv)  # 4
        wait_ok(client)

    send_ok(client)  # 5

    if data_size_recv == 0:
        f = open(file_name, "wb")
    else:
        f = open(file_name, "rb+")

    f.seek(data_size_recv, 0)

    while data_size_recv < size:
        try:
            data = client['socket'].recv(BUFFER_SIZE)
            f.write(data)
            data_size_recv += len(data)
            send_data(client, data_size_recv)
            f.seek(data_size_recv, 0)

        except socket.error as e:
            f.close()
            handle_disconnect(client, "upload", file_name, data_size_recv)
            client['is_closed'] = True
            return

    f.close()


def server_cli():
    while True:
        command = input()
        parsed_data = parse_server_command(command)
        if (parsed_data == False):
            pass
        elif (len(parsed_data) == 2):
            command, body = parsed_data
            handle_server_command(command, body)


def parse_server_command(command):
    command = command.split()
    if len(command) == 0:
        return False

    name_command = command[0]
    if (len(command) == 2):
        body = command[1]
    else:
        body = ""
    return [name_command, body]


def show_clients():
    list_len = len(clients_pool)
    if list_len == 0:
        print("\nNo clients available")
    for i in range(0, list_len):
        print("\n" + "Client " + str(i + 1) + " info: ")
        print("ip: ", clients_pool[i]['ip'])
        print("port: ", clients_pool[i]['port'])
        print("closed: ", clients_pool[i]['is_closed'])


def handle_server_command(command, body):
    if server_commands.get(command) == "help":
        show_server_menu()
    if server_commands.get(command) == "echo":
        print(body)
    if server_commands.get(command) == "show_clients":
        show_clients()
    if server_commands.get(command) == "time":
        print("Server time: " + str(datetime.now())[:19])
    if server_commands.get(command) == "exit":
        server_tcp.close()
        os._exit(1)


def show_server_menu():
    for x in help_list:
        print(x, ": ", help_list[x])


def show_start_message():
    print("Hello, listened on %s:%d" % (IP, PORT))


server_tcp = socket.socket()
server_tcp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

server_tcp.bind((IP, PORT))
server_tcp.listen(1000)

show_start_message()

clients_pool = []
waiting_clients = []

inputs = [server_tcp]

client_ID = 0
process_pool = []


def service(count_busy_processes):
    client, client_info = server_tcp.accept()
    client.setblocking(True)
    client_ip = client_info[0]
    client_port = client_info[1]

    count_busy_processes.value += 1
    print("[PID {} ] Begin process. Busy processes: {}".format(os.getpid(), count_busy_processes.value))

    print("[*] Accepted connection from: %s:%d" % (client_ip, client_port))

    client_obj = {
        "id": client_ID,
        "socket": client,
        "ip": client_ip,
        "is_closed": False,
        "port": client_port
    }

    print("Client :{} multiplexed to PID {}".format(os.getpid(), client_obj['port']))
    while True:
        request = client_obj['socket'].recv(BUFFER_SIZE).decode('utf-8')
        if request:
            request = request.strip()
            if request != '':
                print("[PID {} ] Received: {}".format(os.getpid(), request))
                handle_client_request(client_obj, request)
        else:
            count_busy_processes.value -= 1
            print("[PID {} ] End process. Busy processes: {}".format(os.getpid(), count_busy_processes.value))
            exit_client(client_obj)


POOL = 2
ACTUAL_POOL = POOL

manager = Manager()
count_busy_processes = manager.Value('i', 0)

print("Dispatcher process PID = {}".format(os.getpid()))


def create_service_process(count_busy_processes):
    p = Process(target=service, args=(count_busy_processes,))
    p.start()

    process_pool.append(p)


for i in range(POOL):
    create_service_process(count_busy_processes)

while True:
    if count_busy_processes.value >= ACTUAL_POOL:
        create_service_process(count_busy_processes)
        ACTUAL_POOL += 1
        print("[PID {} ] Increment pool size to {}".format(os.getpid(), ACTUAL_POOL))
    elif ACTUAL_POOL > count_busy_processes.value + 1 and ACTUAL_POOL > POOL:
        ACTUAL_POOL -= 1
        print("[PID {} ] Decrease pool size to {}".format(os.getpid(), ACTUAL_POOL))
    else:
        create_service_process(count_busy_processes)

    sleep(1)
