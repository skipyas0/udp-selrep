from socket import *
import struct
# from io import TextIOWrapper
from crcmod import mkCrcFun
from hashlib import sha1
# from sys import getsizeof

MAX_PACKET_SIZE = 1024
PACKET_HEADER_SIZE = 2 + 2 + 2 + 2  # packet type + length + number of packet + crc
BUFFER_SIZE = MAX_PACKET_SIZE - PACKET_HEADER_SIZE
SEND_DATA = 1
SEND_HASH = 2
# Create 16bit CRC function
crc16 = mkCrcFun(0x18005, rev=False, initCrc=0xFFFF, xorOut=0x0000)


def send_file_selrep(file: str, source: tuple[str, int], target: tuple[str, int], window_size: int) -> None:
    sock = socket(AF_INET, SOCK_DGRAM)
    sock.bind(("0.0.0.0", source[1]))
    sock.settimeout(2)
    f = open(file, "rb")
    pb_sha = sha1()
    sent_packets = {}
    stuff_to_send = True
    curr_packet_num = 1
    send_file = True
    send_packet_num = 0
    next_packet = 0
    # Break on end of file
    while stuff_to_send:

        # Sending packets up to the size of sending window
        while send_file and send_packet_num < window_size:
            data = f.read(BUFFER_SIZE)
            if data:
                pb_sha.update(data)
                packet_type = SEND_DATA
            else:
                data = str.encode(pb_sha.hexdigest())
                send_file = False
                packet_type = SEND_HASH

            data_size = len(data)
            preamble = format(packet_type, '016b') + format(curr_packet_num, '032b')
            # print("size preamble", getsizeof(preamble))
            crc = crc16(preamble.encode('utf-8') + data)
            # Creating packet using struct, H is unsigned short (16bit), I is unsigned integer (32bit)
            packet = struct.pack(f"!HHI{data_size}s", packet_type, crc, curr_packet_num, data)

            # print(struct.unpack(f"!HHHH{data_size}s", packet))
            # print("size packet", getsizeof(packet))
            if sock.sendto(packet, target):
                sent_packets[curr_packet_num] = packet
                print(f"Sent packet number {curr_packet_num}.")
                curr_packet_num += 1
                send_packet_num += 1
            else:
                print(f"Failed to send packet {curr_packet_num}")

        print("Sending window full, awaiting ACK ...")

        # Will wait for ACKs and handle lost packet
        try:
            # sock.settimeout(2)
            new_packet, crc = struct.unpack(f"!IH", sock.recv(48))
            crc_recalc = crc16(format(new_packet, '032b').encode())
            # If ACK asks for previously unsent packet, all previous were successfully delivered
            if crc == crc_recalc:
                next_packet = new_packet
                if next_packet > max(sent_packets.keys()):
                    print(f"Target requests next packet {next_packet}, clearing window")
                    sent_packets = dict()
                    send_packet_num = 0
                    if next_packet > (window_size + 1):
                        curr_packet_num = 1
                    if not send_file:
                        stuff_to_send = False
                else:
                    # Packet got lost, resending
                    print(f"Target requests resend of packet {next_packet}.")
                    if sock.sendto(sent_packets[next_packet], target):
                        print(f"Resent packet number {next_packet}.")
                        send_packet_num = 1
                    else:
                        print(f"Failed to resend packet {next_packet}.")
            else:
                print("ACK crc check failed")
                send_packet_num = 0
                if not send_file:
                    sock.sendto(sent_packets[next_packet], target)
        except timeout:
            print("No ACK.")
            send_packet_num = 0
            if not send_file:
                sock.sendto(sent_packets[next_packet], target)

        print("Continue sending")

    f.close()
    sock.close()
    print("File transferred")


def receive_file_selrep(f_path: str, receiver_port: int, sender: tuple[str, int], window_size: int) -> None:
    sock = socket(AF_INET, SOCK_DGRAM)
    sock.bind(("0.0.0.0", receiver_port))
    sock.settimeout(0.5)
    pb_sha = sha1()
    in_window = 0
    received_packets = {}
    stuff_to_receive = True
    f = open(f_path, "wb+")
    start_packet = 1
    end_packet = -1
    wait = 0
    save_num = 1
    while stuff_to_receive:
        while stuff_to_receive and in_window < window_size:
            try:
                packet, client_address = sock.recvfrom(MAX_PACKET_SIZE)
                length = len(packet) - PACKET_HEADER_SIZE
                packet_type, crc, sequence_number, data = struct.unpack(f"!HHI{length}s", packet)
                preamble = format(packet_type, '016b') + format(sequence_number, '032b')
                crc_recalc = crc16(preamble.encode('utf-8') + data)
                crc_ok = crc == crc_recalc
                if crc_ok and sequence_number < start_packet and not received_packets.keys():
                    start_packet = 1
                if crc_ok and sequence_number not in received_packets.keys() and sequence_number >= start_packet:
                    print(f"Packet number {sequence_number} accepted.")
                    received_packets[sequence_number] = data
                    # last packet arrived
                    if packet_type == SEND_HASH:
                        end_packet = sequence_number
                else:
                    print(f"CRC check failed on packet number {sequence_number}.")
                in_window += 1
            except timeout:
                break

        if received_packets.keys():
            next_expected = max(received_packets.keys()) + 1
            all_the_packets_we_want = list(range(start_packet, next_expected + 1))

            # Filter out packets that we have received successfully, use set to get rid of duplicates
            missing_packets = sorted(set(filter(lambda i: i not in received_packets.keys(), all_the_packets_we_want)))
            print("Missing packets: ", len(missing_packets))

            sequence_number = missing_packets.pop(0)
            in_window = 0
            crc = crc16(format(sequence_number, '032b').encode())
            ack_packet = struct.pack(f"!IH", sequence_number, crc)
            if sock.sendto(ack_packet, sender):
                print(
                    f"Sent ACK with request for {'missing' if sequence_number < next_expected else 'next'} packet number {sequence_number}.")
            else:
                print(
                    f"Failed to send ACK with request for {'missing' if sequence_number < next_expected else 'next'} packet number {sequence_number}.")
            if window_size > 1 and end_packet > 0:
                window_size = 1
            # All packets arrived, close communication
            if end_packet == sequence_number - 1:
                sequence_number -= 1
                while wait < 5:
                    try:
                        sock.recvfrom(MAX_PACKET_SIZE)
                        sock.sendto(ack_packet, sender)
                        wait = 0
                    except timeout:
                        wait += 1
                stuff_to_receive = False

            # Write received packets in the file
            for packet in range(start_packet, sequence_number):
                print(save_num, packet)
                f.write((received_packets[packet]))
                pb_sha.update(received_packets.pop(packet))
                save_num += 1

            start_packet = sequence_number

    f.close()
    sock.close()
    if str.encode(pb_sha.hexdigest()) == received_packets[end_packet]:
        print("SHA matches! Transmission successful")
    else:
        print("SHA mismatched! Transmission failed.")
