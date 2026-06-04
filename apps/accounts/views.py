from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError

from .serializers import SignupSerializer, LoginSerializer, SignupResponseSerializer
from .models import User


class SignupView(APIView):
    """User signup endpoint."""
    
    def post(self, request):
        """Create a new user account."""
        serializer = SignupSerializer(data=request.data)
        
        if serializer.is_valid():
            user = serializer.save()
            response_serializer = SignupResponseSerializer(user)
            return Response(
                response_serializer.data,
                status=status.HTTP_201_CREATED
            )
        
        # Check if error is due to duplicate email
        if 'email' in serializer.errors:
            return Response(
                {'error': 'This email is already registered.'},
                status=status.HTTP_409_CONFLICT
            )
        
        return Response(
            {'error': serializer.errors},
            status=status.HTTP_400_BAD_REQUEST
        )


class LoginView(APIView):
    """User login endpoint."""
    
    def post(self, request):
        """Authenticate user and return tokens."""
        serializer = LoginSerializer(data=request.data)
        
        if serializer.is_valid():
            user = serializer.validated_data['user']
            
            # Generate JWT tokens
            refresh = RefreshToken.for_user(user)
            access_token = str(refresh.access_token)
            
            response = Response(
                {
                    'access_token': access_token,
                    'token_type': 'Bearer',
                },
                status=status.HTTP_200_OK
            )
            
            # Set refresh token as HttpOnly cookie
            response.set_cookie(
                key='refresh_token',
                value=str(refresh),
                httponly=True,
                secure=False,  # Set to True in production
                samesite='Lax',
                max_age=7 * 24 * 60 * 60,  # 7 days
            )
            
            return response
        
        # Handle validation errors with proper HTTP status codes
        errors = str(serializer.errors)
        
        if 'Invalid email or password' in errors:
            return Response(
                {'error': 'Invalid email or password.'},
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        if 'Email not verified' in errors:
            return Response(
                {'error': 'Email not verified.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        if 'Account is suspended' in errors:
            return Response(
                {'error': 'Account is suspended.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        return Response(
            {'error': 'Invalid email or password.'},
            status=status.HTTP_401_UNAUTHORIZED
        )


class CookieTokenRefreshView(APIView):
    """Token refresh endpoint that reads refresh token from HttpOnly cookie."""
    
    def post(self, request):
        """Refresh access token using refresh token from cookie."""
        # Get refresh token from HttpOnly cookie
        refresh_token = request.COOKIES.get('refresh_token')
        
        if not refresh_token:
            return Response(
                {'error': 'Refresh token not found.'},
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        try:
            # Validate and get new access token
            serializer = TokenRefreshSerializer(data={'refresh': refresh_token})
            if serializer.is_valid():
                return Response(
                    {'access_token': serializer.validated_data['access']},
                    status=status.HTTP_200_OK
                )
            else:
                return Response(
                    {'error': 'Invalid or expired refresh token.'},
                    status=status.HTTP_401_UNAUTHORIZED
                )
        except (InvalidToken, TokenError):
            return Response(
                {'error': 'Invalid or expired refresh token.'},
                status=status.HTTP_401_UNAUTHORIZED
            )
        except Exception as e:
            return Response(
                {'error': 'Token refresh failed.'},
                status=status.HTTP_401_UNAUTHORIZED
            )
