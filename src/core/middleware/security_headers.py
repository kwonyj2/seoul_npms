"""추가 보안 헤더 미들웨어"""


class SecurityHeadersMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response['X-Content-Type-Options'] = 'nosniff'
        response['X-XSS-Protection'] = '1; mode=block'
        response['Permissions-Policy'] = 'camera=(self), microphone=(), geolocation=(self)'
        response['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        return response
