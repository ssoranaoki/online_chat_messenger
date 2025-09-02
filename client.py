import json
import os
import socket
import threading


class ChatClient:
    def __init__(
        self, server_host: str = "localhost", tcp_port: int = 8888, udp_port: int = 8889
    ) -> None:
        self.server_host = server_host
        self.tcp_port = tcp_port
        self.udp_port = udp_port
        self.token = None
        self.room_name = None
        self.username = None
        self.operation_room_create = 1  # 1: ルーム作成
        self.operation_room_join = 2  # 2: ルーム参加
        self.operation_list_rooms = 3  # 3: ルーム一覧表示
        self.is_client_running = False
        self.udp_socket = None
        self.my_udp_port = 0  # 自動割り当て

        # TCPソケット作成
        self.tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        # メニュー選択肢の定数
        self.CREATE_ROOM = "1"
        self.JOIN_ROOM = "2"
        self.LIST_ROOMS = "3"
        self.QUIT = "4"

    def start(self):
        """クライアント処理開始"""
        # アプリケーションの案内文を表示
        print("チャットアプリケーションを起動します")
        # プロセスIDを表示
        print(f"クライアントID: {os.getpid()}")
        print("--------------------------------")
        print(f"{self.CREATE_ROOM}. ルームを作成する")
        print(f"{self.JOIN_ROOM}. ルームに参加する")
        print(f"{self.LIST_ROOMS}. ルームを一覧表示する")
        print(f"{self.QUIT}. 終了する")
        print("--------------------------------")

        # クライアントの選択内容を継続的に待ち受ける
        while True:
            user_choice = input("番号を入力してください: ").lower()

            # ユーザーの選択内容に応じて処理を分岐
            match user_choice:
                # ルーム作成
                case self.CREATE_ROOM:
                    self._create_room()
                    break
                # ルーム参加
                case self.JOIN_ROOM:
                    self._join_room()
                    break
                # ルーム一覧表示
                case self.LIST_ROOMS:
                    self._list_rooms()
                    break
                # 終了
                case self.QUIT:
                    return
                # 無効な選択
                case _:
                    print(f"{user_choice}は無効な選択です。選択肢を確認してください")

        # TCPメッセージを受信
        result_boolean_tcp_message = self._receve_tcp_message()
        # print("self._receve_tcp_message():", result_boolean_tcp_message)

        # ルーム一覧表示以外の処理とTCP受信メッセージにエラーが無い場合にUDP接続を開始する
        if user_choice != self.LIST_ROOMS and result_boolean_tcp_message:
            # UDP接続開始
            self._start_udp_chat()

    def _create_room(self):
        """ルーム作成"""
        # ルーム名を入力
        room_name = input("ルーム名を入力してください: ").strip()
        # ユーザー名を入力
        user_name = input("ユーザー名を入力してください: ").strip()

        # ルーム名とユーザー名が正しく入力されているか確認
        if not room_name or not user_name:
            print("ルーム名とユーザー名を入力してください")
            return False

        # UDPソケット作成してUDPポート番号を取得
        if not self._setup_udp_socket():
            return False

        # サーバーにルーム作成リクエストを送信
        self.operation = self.operation_room_create
        # ユーザーに表示
        print(f"作成したいルーム名：{room_name}")
        return self._send_tcp_request(room_name, user_name, self.operation_room_create)

    def _join_room(self):
        """ルームに参加"""

        # ルーム名を入力
        room_name = input("ルーム名を入力してください: ").strip()
        # ユーザー名を入力
        user_name = input("ユーザー名を入力してください: ").strip()

        # ルーム名とユーザー名が正しく入力されているか確認
        if not room_name or not user_name:
            print("ルーム名とユーザー名を入力してください")
            return False
        # UDPソケット作成してUDPポート番号を取得
        if not self._setup_udp_socket():
            return False

        # サーバーにルームに参加リクエストを送信
        self.operation = self.operation_room_join
        return self._send_tcp_request(room_name, user_name, self.operation_room_join)

    def _list_rooms(self):
        """ルーム一覧表示"""
        # サーバーにルーム一覧表示リクエストを送信
        self.operation = self.operation_list_rooms
        return self._send_tcp_request("", "", self.operation_list_rooms)

    def _setup_udp_socket(self):
        """UDPソケットを作成してUDPポート番号を取得"""
        try:
            # UDPソケット作成
            self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            # ポート番号を自動割り当て
            self.udp_socket.bind(("", 0))
            # 自動割り当てされたポート番号を取得
            self.my_udp_port = self.udp_socket.getsockname()[1]
            print(f"UDPポート番号: {self.my_udp_port}")
            return True
        except OSError as e:  # オペレーションシステムエラー
            print(f"UDPソケット処理エラー: {e}")
            return False
        except Exception as e:  # 例外
            print(f"UDPソケット処理エラー: {e}")
            return False

    def _send_tcp_request(self, room_name: str, user_name: str, operation: int) -> bool:
        """TCPリクエストを送信
        ヘッダー：
                1 + 1 + 1 + 29 = 32バイト
                ルーム名, ユーザー名, 操作
        ボディ: ペイロードデータ
                ユーザー名, UDPポート番号
        """
        try:
            # サーバーに接続
            self.tcp_socket.connect((self.server_host, self.tcp_port))
        except ConnectionRefusedError as e:
            print(f"TCP接続エラー: {e}")
            return False
        except OSError as e:
            print(f"TCP接続エラー: {e}")
            return False

        # リクエストデータを作成
        room_name_bytes = room_name.encode("utf-8")
        payload_data = {
            "user_name": user_name,
            "udp_port": self.my_udp_port,
        }
        payload_bytes = json.dumps(payload_data).encode("utf-8")

        # ヘッダーを作成(固定長32バイト)
        header = bytearray(32)
        # ルーム名
        header[0] = len(room_name_bytes)
        # 操作
        header[1] = operation
        # リクエスト
        header[2] = 0
        # ペイロードデータ
        header[3:] = len(payload_bytes).to_bytes(29, "big")

        # ヘッダーとペイロードデータを結合
        request_data = header + room_name_bytes + payload_bytes

        try:
            # データ送信
            self.tcp_socket.sendall(request_data)
            # デバッグ
            # print(f"リクエストデータ：{request_data}")
            # 送信内容をユーザーに表示
            # print(f"TCPリクエストを送信しました: 作成したいルーム名{room_name}")
            return True
        except ConnectionRefusedError as e:
            print(f"TCP接続エラー: {e}")
            return False
        except OSError as e:
            print(f"TCP接続エラー: {e}")
            return False

    def _receve_tcp_message(self):
        """TCPメッセージを受信"""
        # レスポンスを受信
        try:
            # ヘッダー受信
            header = self.tcp_socket.recv(32)

            # ヘッダーの長さ確認
            if len(header) != 32:
                print("ヘッダーの長さが不正です")
                return False

            # ヘッダー
            room_name_length = header[0]
            operation = header[1]
            # state = header[2]
            payload_length = int.from_bytes(header[3:], "big")

            # ボディ受信
            response_data = self.tcp_socket.recv(room_name_length + payload_length)
            # ルームネーム取得(UTF8デコード)
            response_room_name = response_data[:room_name_length].decode("utf-8")
            # ペイロードデータ取得(UTF8デコード)
            response_payload = response_data[room_name_length:].decode("utf-8")

            # TCPソケット閉じる
            self.tcp_socket.close()

            # json形式に変更
            response_json = json.loads(response_payload)
            # デバッグ
            print(f"response_json: {response_json}")

            # レスポンスのステータスを確認して処理
            if response_json.get("status") == "success":
                # トークン、ルーム名、ユーザー名を設定
                self.token = response_json.get("token")
                self.room_name = response_room_name
                self.username = response_json.get("user_name")
                # デバッグ
                # print(f"ルーム名: {self.room_name}")
                # print(f"ユーザー名: {self.username}")
                # print(f"トークン: {self.token}")
                print(f"operation: {operation}")

                # 設定内容をユーザーに表示
                if operation == self.operation_room_create:
                    print("--------------------------------")
                    print(f"ルーム名: {self.room_name} を作成しました")
                    print(f"ユーザー名: {self.username} で参加しました")
                    print(f"トークン: {self.token} を取得しました")
                    print("トークンは大切に保管してください")
                    print("--------------------------------")
                elif operation == self.operation_room_join:
                    print("--------------------------------")
                    print(f"ルーム名: {self.room_name} に参加しました")
                    print(f"ユーザー名: {self.username} で参加しました")
                    print(f"トークン: {self.token} を取得しました")
                    print("トークンは大切に保管してください")
                    print("--------------------------------")
                elif operation == self.operation_list_rooms:
                    print("--------------------------------")
                    print("現在アクティブなルーム一覧:")
                    for index, room in enumerate(response_json.get("message"), start=1):
                        print(f"ルーム{index}: {room}")
                    print("--------------------------------")

                return True
            else:  # エラー時の対応
                print(f"エラー: {response_json.get('message')}")
                # UDPソケットを閉じる
                if self.udp_socket:
                    self.udp_socket.close()
                return False

        except ConnectionRefusedError as e:  # 接続エラー
            print(f"TCP接続エラー: {e}")
            return False
        except OSError as e:  # OSエラー
            print(f"OSエラー: {e}")
            return False
        except Exception as e:  # 例外処理
            print(f"例外処理: {e}")
            return False

    def _start_udp_chat(self):
        """UDPチャットを開始"""
        try:
            self.is_client_running = True

            # メッセージ受信スレッド開始
            receive_thread = threading.Thread(target=self._receve_udp_message)
            receive_thread.daemon = True
            receive_thread.start()

            # UDPソケット作成
            send_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

            print(
                f"\n=== チャットルーム '{self.room_name}' ユーザー名 '{self.username}' ==="
            )
            print("メッセージを入力してください。'/quit' で退出します。\n")

            while self.is_client_running:
                try:
                    # メッセージ入力
                    message = input()

                    # メッセージが'/quit'の場合
                    if message.lower() == "/quit":
                        # /quitの内容でメッセージ送信
                        self._send_udp_message(send_socket, message)
                        self.is_client_running = False
                        break
                    elif message.strip():
                        # メッセージ送信
                        self._send_udp_message(send_socket, message)
                except KeyboardInterrupt:
                    print("\nチャットを終了します")
                    self._send_udp_message(send_socket, "/quit")
                    self.is_client_running = False
                    break
                except Exception as e:
                    print(f"エラーが発生しました: {e}")
                    self._send_udp_message(send_socket, "/quit")
                    self.is_client_running = False
                    break
            send_socket.close()
        except Exception as e:
            print(f"エラーが発生しました: {e}")
        finally:
            # UDPソケットが起動している場合
            if self.udp_socket:
                self.udp_socket.close()
            print("チャットルームを閉じました")

    def _send_udp_message(self, send_socket: socket.socket, message: str):
        """UDPメッセージを送信"""
        try:
            # 送信データのエンコード処理
            room_name_bytes = self.room_name.encode("utf-8")  # type:ignore
            token_bytes = self.token.encode("utf-8")  # type:ignore
            message_bytes = message.encode("utf-8")

            # UDPパケット作成
            packet = bytearray()
            packet.append(len(room_name_bytes))
            packet.append(len(token_bytes))
            packet.extend(room_name_bytes)
            packet.extend(token_bytes)
            packet.extend(message_bytes)

            # パケット送信
            send_socket.sendto(packet, (self.server_host, self.udp_port))

        except OSError as e:  # OSエラー
            print(f"UDPメッセージ送信エラー: {e}")
        except Exception as e:  # 例外処理
            print(f"UDPメッセージ送信エラー: {e}")

    def _receve_udp_message(self):
        """UDPメッセージを受信"""
        while self.is_client_running:
            try:
                # メッセージを受信
                data, client_address = self.udp_socket.recvfrom(4096)  # type:ignore
                message = data.decode("utf-8")

                # 受信したメッセージを表示
                print(f"{message}")
                # if "[システム]" in message:
                #     print("ok")
                # if "ルームが閉じられました" in message:
                #     print("ok")

                # 受信したメッセージの内容にルームが閉じられた事が含まれている場合の処理
                if "ホストが退出したため" in message:
                    print("ルームが閉じられました")
                    print("エンターキーを押してください")
                    self.is_client_running = False
                    break
            except OSError as e:  # OSエラー
                print(f"UDPソケット処理エラー: {e}")
                break
            except Exception as e:  # 例外処理
                print(f"UDPソケット処理エラー: {e}")
                break


# メイン処理
if __name__ == "__main__":
    try:
        # クライアントインスタンスを作成
        client = ChatClient()
        # クライアントを起動
        client.start()
    except KeyboardInterrupt:
        print("\nチャットアプリケーションを終了します")
    except Exception as e:
        print(f"\nエラーが発生しました: {e}")
