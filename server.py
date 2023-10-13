from aiohttp import web

MAX_COUNT_OF_URLS = 10


async def handle(request):
    urls = request.query.get("urls", "").split(",")
    if len(urls) > MAX_COUNT_OF_URLS:
        error_message = (
            f"too many urls in request, should be {MAX_COUNT_OF_URLS} or less"
        )
        return web.json_response({"error": error_message}, status=400)

    return web.json_response(urls)


app = web.Application()
app.add_routes([web.get("/", handle), web.get("/{name}", handle)])

if __name__ == "__main__":
    web.run_app(app)
