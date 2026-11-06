"""Safe, short descriptions of failed provider checks for Telegram."""
import httpx


def describe_check_error(error: Exception) -> str:
    if isinstance(error, httpx.TimeoutException):
        return "Превышено время ожидания ответа источника"
    if isinstance(error, httpx.ConnectError):
        return "Не удалось установить соединение с источником"
    if isinstance(error, httpx.HTTPStatusError):
        code = error.response.status_code
        descriptions = {
            401: "неверный ключ доступа или требуется авторизация",
            403: "доступ запрещён или превышен лимит запросов",
            404: "репозиторий или выпуски не найдены",
            429: "превышен лимит запросов",
        }
        return f"HTTP {code}: {descriptions.get(code, 'ошибка ответа источника')}"
    if isinstance(error, httpx.RequestError):
        return "Сетевая ошибка при обращении к источнику"
    # Never echo arbitrary exception strings: they can contain tokens or private URLs.
    if isinstance(error, (ValueError, RuntimeError)):
        return f"Ошибка обработки данных источника ({type(error).__name__})"
    return f"Неожиданная ошибка ({type(error).__name__})"
