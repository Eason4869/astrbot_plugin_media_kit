import asyncio
from io import BytesIO
from pathlib import Path
import tempfile
import unittest
from PIL import Image
import support
from core.rika_render.downloader import _download_one


class TestCardDownloadSecurity(unittest.IsolatedAsyncioTestCase):
    async def test_card_image_does_not_connect_to_private_address(self):
        image = BytesIO()
        Image.new("RGB", (16, 16)).save(image, format="PNG")
        data = image.getvalue()
        connections = []
        async def serve(reader, writer):
            connections.append(True)
            await reader.read(8192)
            writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: image/png\r\nContent-Length: "
                         + str(len(data)).encode() + b"\r\nConnection: close\r\n\r\n" + data)
            await writer.drain()
            writer.close()
            await writer.wait_closed()
        server = await asyncio.start_server(serve, "127.0.0.1", 0)
        try:
            port = server.sockets[0].getsockname()[1]
            with tempfile.TemporaryDirectory() as directory:
                result = await _download_one(f"http://127.0.0.1:{port}/image.png", Path(directory), {})
            self.assertIsNone(result)
            self.assertEqual(connections, [])
        finally:
            server.close()
            await server.wait_closed()
