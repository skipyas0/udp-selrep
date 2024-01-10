import argparse
from client_utils import send_file_selrep

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        prog="Sender client",
        description="Sends given file to target address using UDP with Selective-Repeat"
    )
    parser.add_argument("file", type=str,  help="file to be sent")
    parser.add_argument("source_address", type=str, help="specify source address")
    parser.add_argument("source_port", type=int, help="specify source port")
    parser.add_argument("target_address", type=str, help="specify target address")
    parser.add_argument("target_port", type=int, help="specify target port")
    parser.add_argument("-window", dest="window", type=int, required=False, default=10, help="sent packets limit")
    args = parser.parse_args()

    source = (args.source_address, args.source_port)
    target = (args.target_address, args.target_port)
    print(source, target)
    send_file_selrep(args.file, source, target, args.window)
