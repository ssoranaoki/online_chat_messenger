import json
import socket
import threading
import time
import uuid
from typing import Any, Dict, Tuple


class ChatRoom:
    """チャットルームクラス:
    チャットルームの名前、ホストのトークン、参加者のトークン、作成時間を管理する"""

    def __init__(self, room_name, host_token):
        self.room_name = room_name
        self.host_token = host_token
        # ユーザー管理システム：各ユーザーはUUID4で生成されたユニークなトークンで識別される
        # トークンには以下の情報が紐づけられて管理される：
        # - ユーザー名：チャット画面に表示される名前
        # - IPアドレス：クライアントの接続元IP（セキュリティ検証用）
        # - UDPポート：メッセージ送受信用のクライアントUDPポート番号
        # {token: (user_name, ip, port)}
        self.tokens: Dict[str, Tuple[str, str, int]] = {}
        self.created_at = time.time()

    def add_user(self, token: str, user_name: str, ip: str, port: int) -> None:
        """ユーザーを追加する"""
        self.tokens[token] = (user_name, ip, port)

    def remove_user(self, token: str) -> None:
        """ユーザーを削除する"""
        # ユーザーが存在する場合
        if token in self.tokens:
            # ユーザーを削除
            del self.tokens[token]

    def is_host(self, token: str) -> bool:
        """チャットルームのホストかどうか確認する"""
        return token == self.host_token

    def validated_token(self, token: str, ip: str) -> bool:
        """トークンとipの検証"""
        return token in self.tokens and self.tokens[token][1] == ip

    def get_udp_sender_address(self, token: str) -> tuple[str, int]:
        """UDP送信者のアドレスを取得する"""
        # トークンが存在する場合
        if token in self.tokens:
            # トークンに紐づけられたIPアドレスとUDPポート番号を取得
            _, ip, port = self.tokens[token]
            # アドレスを返す
            return (ip, port)
        else:  # トークンが見つからない場合
            # エラーメッセージを返す
            raise ValueError(
                "無効なトークンです。チャットルームに参加している有効なトークンを指定してください"
            )


class ChatServer:
    def __init__(self, tcp_port: int = 8888, udp_port: int = 8889) -> None:
        self.tcp_port = tcp_port
        self.udp_port = udp_port
        self.chat_rooms: Dict[str, ChatRoom] = {}
        self.is_server_running = True
        self.client_addresses: Dict[str, Tuple[str, int]] = {}  # {token: (ip, port)}

    def server_start(self):
        """サーバーを起動する"""
        # TCPサーバーをバックグラウンドスレッドで起動する
        tcp_thread = threading.Thread(target=self._tcp_server)
        tcp_thread.daemon = True
        tcp_thread.start()

        # UDPサーバーをバックグラウンドスレッドで起動する
        udp_thread = threading.Thread(target=self._udp_server)
        udp_thread.daemon = True
        udp_thread.start()

        # サーバー起動を表示
        print(f"TCPサーバーが起動しました。ポート：{self.tcp_port}")

        # メインスレッドを継続させてプログラムを実行状態に保つ
        # TCPサーバーは別スレッドで動作するため、メインスレッドが終了すると
        # プログラム全体が終了してしまう。そのため、ここでメインスレッドを
        # 待機状態にしてサーバーの稼働を継続させる
        try:
            while self.is_server_running:
                time.sleep(1)  # CPU負荷を下げるため1秒間待機
        except KeyboardInterrupt:  # ctrl+cキー操作対応
            print("サーバーを停止中です。。。。。")
            # メインスレッド停止
            self.is_server_running = False
            print("サーバーを停止しました")

    def _tcp_server(self):
        """TCPServerを起動する"""
        # TCPソケットを作成
        tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # ソケットオプション設定：アドレスを再利用可能にする
        tcp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # 指定されたポートにソケットをバインド
        tcp_socket.bind(("0.0.0.0", self.tcp_port))
        # 接続待ちキューの最大数を設定
        tcp_socket.listen(5)

        # クライアントからの接続を継続的に待ち受ける
        while self.is_server_running:
            try:
                # クライアントからの接続要求を受け入れる（ブロッキング処理）
                client_socket, client_address = tcp_socket.accept()
                # 各クライアントの処理を別スレッドで実行（非同期処理）
                threading.Thread(
                    target=self._handle_tcp_client, args=(client_socket, client_address)
                ).start()
            except Exception as e:
                # サーバー停止中でない場合のみエラーを表示する
                if self.is_server_running:
                    print(f"エラーが発生しました: {e}")
                    self.is_server_running = False
            except KeyboardInterrupt:
                print("TCPサーバーが停止しました")
                self.is_server_running = False

        # サーバー終了時の処理
        tcp_socket.close()
        print("TCPソケットを閉じました")

    def _handle_tcp_client(
        self, client_socket: socket.socket, client_address: tuple[str, int]
    ) -> None:
        """TCPクライアントリクエスト処理"""
        try:
            # ヘッダーを受信する（32バイト）
            header_data = client_socket.recv(32)

            # ヘッダーの各フィールドを解析
            room_name_size = header_data[0]  # ルーム名のサイズ（1バイト）
            operation = header_data[1]  # 操作タイプ（1バイト）
            state = header_data[2]  # 状態（1バイト）
            payload_data_size = int.from_bytes(
                header_data[3:32], "big"
            )  # ペイロードサイズ（29バイト）
            # print(f"room_name_size: {room_name_size}")
            # print(f"operation: {operation}")
            # print(f"state: {state}")
            # print(f"payload_data_size: {payload_data_size}")

            # ボディデータ（ルーム名とその他のデータ）を受信する
            expected_body_size = room_name_size + payload_data_size
            body_data = b""
            body_data = client_socket.recv(expected_body_size)
            # print(f"ボディデータ：{body_data}")

            # ボディデータからルーム名部分を抽出してUTF-8でデコードする
            room_name = body_data[:room_name_size].decode("utf-8")
            # print(f"ルーム名：{room_name}")

            # ペイロードデータが存在する場合
            if payload_data_size > 0:
                try:
                    # ボディデータからペイロードデータを抽出してデコードする
                    payload_data = body_data[room_name_size:].decode("utf-8")
                    print(f"受信したペイロードデータ: '{payload_data}'")
                    # ペイロードデータをJSON形式に変換
                    payload_json = json.loads(payload_data)
                    # ユーザー名を取得
                    user_name = payload_json.get("user_name", "")
                    # クライアントのUDPポートを取得
                    client_udp_port = payload_json.get("udp_port", 0)
                except UnicodeDecodeError as e:  # ペイロードデータがUTF-8でない場合
                    print(f"UTF-8デコードエラー: {e}")
                    user_name = ""
                    client_udp_port = 0
                except json.JSONDecodeError as e:  # ペイロードデータがJSON形式でない場合
                    print(f"JSON解析エラー: {e}")
                    user_name = ""
                    client_udp_port = 0
                except Exception as e:  # その他の予期しないエラー
                    print(f"予期しないエラー: {e}")
                    user_name = ""
                    client_udp_port = 0
            else:  # ペイロードデータが存在しない場合の値を設定
                user_name = ""
                client_udp_port = 0

            # デバッグ
            print(f"room_name: {room_name}")
            print(f"operation: {operation}")
            print(f"state: {state}")
            print(f"user_name: {user_name}")
            print(f"client_udp_port: {client_udp_port}")

            # 受信データのリクエスト確認
            if state == 0:
                # 新規チャットルーム作成
                if operation == 1:
                    response_data = self._create_room(
                        room_name, user_name, client_address[0], client_udp_port
                    )
                elif operation == 2:  # ルームに参加
                    response_data = self._join_room(
                        room_name, user_name, client_address[0], client_udp_port
                    )
                elif operation == 3:  # ルーム一覧表示
                    response_data = self._list_rooms()
                else:  # 例外処理
                    response_data = {
                        "state": 1,
                        "status": "error",
                        "message": "不正な操作です",
                    }

                # レスポンスデータをクライアントに送信
                if response_data is not None:  # レスポンスデータが存在する場合
                    self._sned_tcp_response(
                        client_socket, room_name, operation, response_data
                    )

        except Exception as e:
            print(f"エラーが発生しました: {e}")
        finally:
            client_socket.close()

    def _create_room(
        self, room_name: str, user_name: str, ip: str, udp_port: int
    ) -> dict[str, Any] | None:
        """新規チャットルームを作成する"""
        # ルームが作成済かどうか確認する
        if room_name in self.chat_rooms:
            return {"state": 1, "status": "error", "message": "ルームが作成済みです"}

        # ホスト用トークン作成
        host_token: str = str(uuid.uuid4())

        # ルーム作成処理
        room = ChatRoom(room_name, host_token)
        room.add_user(host_token, user_name, ip, udp_port)  # ホストをルームに追加
        self.chat_rooms[room_name] = room  # ルームを追加

        # クラインアントアドレスと保存
        self.client_addresses[host_token] = (ip, udp_port)

        # サーバーにルーム作成を通知する
        print(f"ユーザー名：{user_name}によってルーム名：{room_name}が作成されました")

        # クライアントにレスポンスを送信する
        return {
            "state": 2,
            "status": "success",
            "token": host_token,
            "user_name": user_name,
            "message": f"ルーム名：{room_name}が作成されました",
        }

    def _join_room(
        self, room_name: str, user_name: str, ip: str, udp_port: int
    ) -> dict[str, Any] | None:
        """ルームに参加する"""
        # ルームが存在するか確認する
        if room_name not in self.chat_rooms:
            return {"state": 1, "status": "error", "message": "ルームが存在しません"}

        # 作成済みのチャットルームの情報取得
        room = self.chat_rooms[room_name]

        # 新規ユーザー用のトークン作成
        user_token: str = str(uuid.uuid4())

        # ルームに参加する
        room.add_user(user_token, user_name, ip, udp_port)

        # クラインアントアドレスと保存
        self.client_addresses[user_token] = (ip, udp_port)

        # サーバーにルーム参加を通知する
        print(f"ユーザー名：{user_name}がルーム名：{room_name}に参加しました")

        # クライアントにレスポンスを送信する
        return {
            "state": 2,
            "status": "success",
            "token": user_token,
            "user_name": user_name,
            "message": f"ルーム名：{room_name}に参加しました",
        }

    def _list_rooms(self) -> dict[str, Any] | None:
        """ルーム一覧表示"""
        print(f"ルーム一覧: {list(self.chat_rooms.keys())}")
        return {"state": 2, "status": "success", "message": list(self.chat_rooms.keys())}

    def _sned_tcp_response(
        self,
        client_socket: socket.socket,
        room_name: str,
        operation: int,
        response_data: dict[str, Any],
    ):
        """TCPレスポンスを送信する"""
        try:
            # レスポンスデータをJSON形式に変換
            response_json = json.dumps(response_data)
            # レスポンスデータをUTF-8でエンコード
            response_bytes = response_json.encode("utf-8")
            # ルーム名をUTF-8でエンコード
            room_name_bytes = room_name.encode("utf-8")

            # ヘッダーを作成
            header_data = bytearray(32)
            header_data[0] = len(room_name_bytes)
            header_data[1] = operation
            header_data[2] = response_data.get("state", 0)
            header_data[3:32] = len(response_bytes).to_bytes(29, "big")

            # デバッグ
            # print(f"header: {header_data}")
            # print(f"room_name: {room_name_bytes}")
            # print(f"response: {response_bytes}")

            # ヘッダーとボディデータを結合してクライアントに送信
            client_socket.sendall(header_data + room_name_bytes + response_bytes)

        except ConnectionRefusedError as e:  # 接続エラー
            print(f"TCP接続エラー: {e}")
        except OSError as e:  # オペレーションエラー
            print(f"TCP接続エラー: {e}")
        except Exception as e:  # 例外処理
            print(f"TCPレスポンス送信エラー: {e}")

    def _udp_server(self):
        """UDPサーバーを起動する"""
        # UDPソケットを作成
        udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # ソケットオプション設定：アドレスを再利用可能にする
        udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # 指定されたポートにソケットをバインド
        udp_socket.bind(("0.0.0.0", self.udp_port))
        # クライアントからの接続を継続的に待ち受ける
        while self.is_server_running:
            try:
                # クライアントからのデータを受信
                data, client_address = udp_socket.recvfrom(4096)
                # デバッグ
                print(f"data: {data}")
                print(f"client_address: {client_address}")

                # 受信したデータから各データを取得
                room_name_size = data[0]
                token_size = data[1]
                room_name = data[2 : 2 + room_name_size].decode("utf-8")
                token = data[2 + room_name_size : 2 + room_name_size + token_size].decode(
                    "utf-8"
                )
                message = data[2 + room_name_size + token_size :].decode("utf-8")

                # デバッグ
                print(f"room_name: {room_name}")
                print(f"token: {token}")
                print(f"message: {message}")

                # 他のユーザーにメッセージ送信
                self._relay_message(room_name, token, message, client_address, udp_socket)

                # データを表示
            except OSError as e:  # OSエラー
                print(f"UDPサーバー処理エラー: {e}")
            except Exception as e:  # 例外処理
                print(f"UDPサーバー処理エラー: {e}")
        # サーバー終了時の処理
        udp_socket.close()

    def _relay_message(
        self,
        room_name: str,
        token: str,
        message: str,
        sender_address,
        udp_socket: socket.socket,
    ):
        """受信メッセージを他のユーザーに中継"""
        # チャットルームの確認
        if room_name not in self.chat_rooms:
            return

        # 既存のチャットルームの情報取得
        room = self.chat_rooms[room_name]

        # トークンとipのバリデーションチェック
        if not room.validated_token(token, sender_address[0]):
            print(f"無効なIPアドレス{sender_address}とトークン{token}です")

        # 送信してきたユーザー名を取得
        sender_user_name = room.tokens[token][0]

        # /quitコマンドの処理
        if message.lower() == "/quit":
            # ホストが送ってきた場合チャットルーム閉じる
            if room.is_host(token):
                print(
                    f"ホスト{sender_user_name}が退出しました。ルーム{room_name}を閉じています....."
                )
                # 他の全ユーザーに終了通知を知らせるメッセージ
                quit_message: str = f"[システム]: ホストが退出したため、ルーム:{room_name}が閉じられました"
                quit_bytes = quit_message.encode("utf-8")

                # メッセージを送信者以外に送信
                for user_token, (user_name, ip, port) in room.tokens.items():
                    if user_token != token:
                        try:
                            udp_socket.sendto(quit_bytes, (ip, port))
                        except Exception as e:
                            print(
                                f"ユーザー：{user_name}へのメッセージ送信に失敗しました。エラー内容: {e}"
                            )

                # チャットルームを完全削除
                del self.chat_rooms[room_name]

                # 参加者のトークンを削除
                # 全ユーザートークンを取得
                tokens_to_remove = list(room.tokens.keys())
                # クライアントアドレス辞書に存在するか確認
                for token in tokens_to_remove:
                    if token in self.client_addresses:
                        # トークンとアドレス情報を削除
                        del self.client_addresses[token]
            else:  # 一般ユーザーの場合
                print(f"{sender_user_name} がルーム:{room_name}を退出しました")
                # チャットルームからユーザーを削除
                room.remove_user(token)
                # サーバーの情報からも削除
                if token in self.client_addresses:
                    del self.client_addresses[token]

                # 退出通知メッセージを作成
                leave_message = f"[システム]: {sender_user_name}が退出しました"
                leave_message_bytes = leave_message.encode("utf-8")

                # 残りの全ユーザーに退出メッセージを送信
                for user_token, (user_name, ip, port) in room.tokens.items():
                    try:
                        udp_socket.sendto(leave_message_bytes, (ip, port))
                    except Exception as e:
                        print(
                            f"{user_name}へのメッセージ送信に失敗しました。エラー内容：{e}"
                        )
            return
        else:
            # /quit以外のメッセージの処理
            # 「ユーザー名」「メッセージ」のメッセージフォーマット作成
            formated_message = f"[{sender_user_name}]: {message}"
            formated_message_bytes = formated_message.encode("utf-8")

            # ログ出力
            print(f"ルーム：{room_name}　メッセージ：{formated_message}")

            # 送信者以外の全ユーザーに送信
            for user_token, (user_name, ip, port) in room.tokens.items():
                if user_token != token:
                    try:
                        udp_socket.sendto(formated_message_bytes, (ip, port))
                    except Exception as e:
                        print(
                            f"{user_name}へのメッセージ送信に失敗しました。エラー内容：{e}"
                        )


# メイン処理
if __name__ == "__main__":
    # サーバーインスタンスを作成
    server = ChatServer()
    # サーバーを起動
    server.server_start()
