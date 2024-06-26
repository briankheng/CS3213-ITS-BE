from allauth.socialaccount.views import SignupView as AllauthSignupView
from django.contrib.auth import logout
from django.db import IntegrityError
from django.db.models import F
from django.http import HttpRequest, HttpResponsePermanentRedirect
from rest_framework import generics, serializers, status, views
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken

from ..permission_classes import IsManager, IsStudent, IsTutor
from .models import CustomUser, Teaches
from .serializers import (
    RetrieveUserSerializer,
    SignInSerializer,
    SignUpSerializer,
    UpdateUserInfoSerializer,
)


def generate_tokens_for_user(user):
    refresh = RefreshToken.for_user(user)
    return {
        "refresh": str(refresh),
        "access": str(refresh.access_token),
    }


class SignUpView(generics.CreateAPIView):
    permission_classes = [
        AllowAny,
    ]
    serializer_class = SignUpSerializer

    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
        except serializers.ValidationError as e:
            return Response(
                data={"message": e.detail}, status=status.HTTP_400_BAD_REQUEST
            )
        try:
            serializer.save()
        except IntegrityError as e:
            return Response(
                data={"message": e.args}, status=status.HTTP_400_BAD_REQUEST
            )
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class LoginView(views.APIView):
    permission_classes = [
        AllowAny,
    ]
    serializer_class = SignInSerializer

    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
            user = CustomUser.objects.get(email=serializer.data["email"])
            tokens = generate_tokens_for_user(user)
            return Response(
                data={"tokens": tokens, "user": serializer.data},
                status=status.HTTP_200_OK,
            )
        except serializers.ValidationError as e:
            return Response(
                data={"message": e.detail}, status=status.HTTP_400_BAD_REQUEST
            )


class LogoutView(views.APIView):
    permission_classes = [
        IsAuthenticated,
    ]

    def post(self, request):
        refresh_token = request.data.get("tokens", {}).get("refresh")
        if not refresh_token:
            return Response(
                {"error": "Refresh token is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            refresh_token = RefreshToken(refresh_token)
            refresh_token.blacklist()
            logout(request)
            return Response(
                {"message": "User successfully logged out"}, status=status.HTTP_200_OK
            )
        except Exception as e:
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class CustomRedirect(HttpResponsePermanentRedirect):
    allowed_schemes = ["http", "https"]


class CustomSignupView(AllauthSignupView):
    """
    Override allauth social signup view such that when a user attempts to third party signup with an existing email,
    they gets logged in directly and redirected back to frontend
    """

    http_method_names = ["get"]

    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        social_login_email = self.sociallogin.user.email
        if CustomUser.objects.filter(email=social_login_email).exists():
            user = CustomUser.objects.get(email=social_login_email)
            tokens = generate_tokens_for_user(user)
            redirect_url = f'http://localhost:3000/en/auth/post-social-auth?access={tokens["access"]}&refresh={tokens["refresh"]}'
            return CustomRedirect(redirect_url)
        # TODO: What to do here?
        raise Exception()


class SocialCallbackView(generics.GenericAPIView):
    permission_classes = [
        IsAuthenticated,
    ]

    def get(self, request):
        user = request.user
        tokens = generate_tokens_for_user(user)
        redirect_url = f'http://localhost:3000/en/auth/post-social-auth?access={tokens["access"]}&refresh={tokens["refresh"]}'
        return CustomRedirect(redirect_url)


class RetrieveUserView(generics.GenericAPIView):
    permission_classes = [
        IsAuthenticated,
    ]
    serializer_class = RetrieveUserSerializer

    def get(self, request):
        user = request.user
        serializer = self.serializer_class(instance=user)
        try:
            return Response(
                data=serializer.data,
                status=status.HTTP_200_OK,
            )
        except serializers.ValidationError as e:
            return Response(
                data={"message": e.detail}, status=status.HTTP_400_BAD_REQUEST
            )


class ChangePasswordView(views.APIView):
    permission_classes = [
        IsAuthenticated,
    ]

    def post(self, request):
        """
        Example request:
        {
            "old_password": "sampleOldPassword123",
            "new_password": "sampleNewPassword456"
        }
        """

        # Get current user and payload data
        user: CustomUser = request.user
        old_password = request.data.get("old_password")
        new_password = request.data.get("new_password")

        # Check if old_password and new_password are provided in request data
        if not old_password or not new_password:
            return Response(
                {"error": "Old password and new password are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Verify old password
        if not user.check_password(old_password):
            return Response(
                {"error": "Invalid old password"}, status=status.HTTP_400_BAD_REQUEST
            )

        # Set new password
        user.set_password(new_password)
        user.save()

        return Response(
            {"message": "Password updated successfully"}, status=status.HTTP_200_OK
        )


class RetrieveStudentsView(views.APIView):
    permission_classes = [IsTutor | IsManager]
    serializer_class = RetrieveUserSerializer

    def get_all_students(self):
        students = CustomUser.objects.filter(is_student=True)
        serialized_students = self.serializer_class(students, many=True).data
        return Response({"user": serialized_students}, status=status.HTTP_200_OK)

    def get_students_by_ids(self, student_ids: list[str]):
        """
        Example response (list of serialized CustomUser in JSON)
        {
            "user": [
                serialized_CustomUser1,
                serialized_CustomUser2,
                ...
            ]
        }
        """
        if len(student_ids) == 1 and "," in student_ids[0]:
            student_ids = student_ids[0].replace(" ", "").split(",")

        try:
            student_ids: list[int] = [int(s_id) for s_id in student_ids]
        except ValueError:
            return Response(
                {"error": "Student ID must be an integer"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        students = CustomUser.objects.filter(id__in=student_ids)
        try:
            serialized_data = [
                self.serializer_class(s).data for s in students if s.is_student
            ]
        except serializers.ValidationError as e:
            return Response(
                data={"error": e.detail}, status=status.HTTP_400_BAD_REQUEST
            )

        return Response({"user": serialized_data}, status=status.HTTP_200_OK)

    def get_students_by_tutor(self, tutor_id: str, invert: str):
        """
        Example response (list of serialized CustomUser in JSON)
        {
            "user": [
                serialized_CustomUser1,
                serialized_CustomUser2,
                ...
            ]
        }
        """
        if not tutor_id.isdigit():
            return Response(
                {"error": "Tutor ID must be an integer"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        tutor_id: int = int(tutor_id)
        invert: bool = invert.lower() == "true"

        students_taught_by_tutor = Teaches.objects.filter(tutor=tutor_id).values_list(
            "student", flat=True
        )
        if invert:
            students = CustomUser.objects.exclude(
                id__in=students_taught_by_tutor
            ).filter(is_student=True)
        else:
            students = CustomUser.objects.filter(id__in=students_taught_by_tutor)

        try:
            serialized_data = self.serializer_class(students, many=True).data
        except serializers.ValidationError as e:
            return Response(
                data={"error": e.detail}, status=status.HTTP_400_BAD_REQUEST
            )

        return Response({"user": serialized_data}, status=status.HTTP_200_OK)

    def get(self, request: HttpRequest):
        """
        Example url query string
        1. /students
        2. /students?student_ids=1
        3. /students?student_ids=1,2,3
        4. /students?student_ids=1&student_ids=2&student_ids=3
        5. /students?tutor_id=10
        6. /students?tutor_id=10&invert=true

        Example response for each query (assuming all are valid queries)
        1. All CustomUsers with is_student=True
        2. CustomUser with id=1 and is_student=True
        3. Three CustomUsers with id in (1, 2, 3) and is_student=True
        4. Same as the above
        5. n CustomUsers that are taught by tutor with id=10
        6. m CustomUsers that are NOT taught by tutor with id=10
            -> so that tutors can potentially add them in their class (?)

        If multiple GET params are specified, it will be evaluated in the
        order mentioned above
        """
        url_query = request.GET

        if not url_query:
            return self.get_all_students()

        student_ids = url_query.getlist("student_ids")
        tutor_id = url_query.get("tutor_id")
        invert = url_query.get("invert", default="false")

        if student_ids:
            return self.get_students_by_ids(student_ids)
        if tutor_id:
            return self.get_students_by_tutor(tutor_id, invert)

        return Response(
            {"error": "No student or tutor ids provided"},
            status=status.HTTP_400_BAD_REQUEST,
        )


class PromoteStudentsView(views.APIView):
    """
    Promotes students to tutors by managers only

    HTTP Request
        POST students/promote

    Example Payloads
        {"student_ids": [1]}
        {"student_ids": [1, 2, 3]}
    """

    permission_classes = [IsManager]

    def post(self, request: HttpRequest):
        payload = request.data
        ids = payload.get("student_ids")

        if not ids:
            return Response(
                {"error": "Missing 'student_ids' key in payload"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not isinstance(ids, list) or not any(isinstance(_id, int) for _id in ids):
            return Response(
                {"error": "Value of 'student_ids' must be an array of integers"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Retrieve unique IDs
        ids = set(ids)

        # Retrieve all CustomUsers with ID in student_ids
        students = CustomUser.objects.filter(id__in=ids, is_student=True)
        student_ids = set(students.values_list("id", flat=True))

        # Promote students to tutors
        #   If user is a superuser or a manager, keep their is_student status
        #   Else, set to false
        students.update(
            is_student=F("is_superuser") or F("is_manager"),
            is_tutor=True,
        )

        not_students = None
        if len(ids) != len(student_ids):
            not_students = ids - student_ids

        data = {"message": "Successfully promoted students to tutors"}
        if not_students:
            data["warning"] = {
                "message": "These users were not promoted as they do not exist or are not students",
                "ids": not_students,
            }

        return Response(
            data,
            status=status.HTTP_200_OK,
        )


class DemoteStudentsView(views.APIView):
    """
    Demotes tutors to students by managers only

    HTTP Request
        POST tutors/promote

    Example Payloads
        {"tutor_ids": [11]}
        {"tutor_ids": [11, 12, 13]}
    """

    permission_classes = [IsManager]

    def post(self, request: HttpRequest):
        payload = request.data
        ids = payload.get("tutor_ids")

        if not ids:
            return Response(
                {"error": "Missing 'tutor_ids' key in payload"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not isinstance(ids, list) or not any(isinstance(_id, int) for _id in ids):
            return Response(
                {"error": "Value of 'tutor_ids' must be an array of integers"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Retrieve unique IDs
        ids = set(ids)

        # Retrieve all CustomUsers with ID in tutor_ids
        tutors = CustomUser.objects.filter(id__in=ids, is_tutor=True)
        tutor_ids = set(tutors.values_list("id", flat=True))

        # Demote tutors to students
        #   If user is a superuser or a manager, keep their is_tutor status
        #   Else, set to false
        tutors.update(
            is_student=True,
            is_tutor=F("is_superuser") or F("is_manager"),
        )

        not_tutors = None
        if len(ids) != len(tutor_ids):
            not_tutors = ids - tutor_ids

        data = {"message": "Successfully demoted tutors to students"}
        if not_tutors:
            data["warning"] = {
                "message": "These users were not demoted as they do not exist or are not tutors",
                "ids": not_tutors,
            }

        return Response(
            data,
            status=status.HTTP_200_OK,
        )


class RetrieveTutorsView(views.APIView):
    permission_classes = [IsTutor | IsManager]
    serializer_class = RetrieveUserSerializer

    def get_all_tutors(self):
        tutors = CustomUser.objects.filter(is_tutor=True)
        serialized_tutors = [self.serializer_class(t).data for t in tutors]
        return Response({"user": serialized_tutors}, status=status.HTTP_200_OK)

    def get_tutors_by_ids(self, tutor_ids: list[str]):
        """
        Example response (list of serialized CustomUser in JSON)
        {
            "user": [
                serialized_CustomUser1,
                serialized_CustomUser2,
                ...
            ]
        }
        """
        if len(tutor_ids) == 1 and "," in tutor_ids[0]:
            tutor_ids = tutor_ids[0].replace(" ", "").split(",")

        try:
            tutor_ids: list[int] = [int(t_id) for t_id in tutor_ids]
        except ValueError:
            return Response(
                {"error": "Tutor ID must be an integer"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        tutors = CustomUser.objects.filter(id__in=tutor_ids)
        try:
            serialized_data = [
                self.serializer_class(t).data for t in tutors if t.is_tutor
            ]
        except serializers.ValidationError as e:
            return Response(
                data={"error": e.detail}, status=status.HTTP_400_BAD_REQUEST
            )

        return Response({"user": serialized_data}, status=status.HTTP_200_OK)

    def get_tutors_of_student(self, student_id: str):
        """
        Example response (list of serialized CustomUser in JSON)
        {
            "user": [
                serialized_CustomUser1,
                serialized_CustomUser2,
                ...
            ]
        }
        """
        if not student_id.isdigit():
            return Response(
                {"error": "Student ID must be an integer"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        student_id: int = int(student_id)
        tutors_of_student = Teaches.objects.filter(student=student_id).select_related(
            "tutor"
        )

        try:
            serialized_data = [
                self.serializer_class(t.tutor).data for t in tutors_of_student
            ]
        except serializers.ValidationError as e:
            return Response(
                data={"error": e.detail}, status=status.HTTP_400_BAD_REQUEST
            )

        return Response({"user": serialized_data}, status=status.HTTP_200_OK)

    def get(self, request: HttpRequest):
        """
        Example url query string
        1. /tutors
        2. /tutors?tutor_ids=10
        3. /tutors?tutor_ids=10,20,30
        4. /tutors?tutor_ids=10&tutor_ids=20&tutor_ids=30
        5. /tutors?student_id=1

        Example response for each query (assuming all are valid queries)
        1. All CustomUsers with is_tutor=True
        2. CustomUser with id=10 and is_tutor=True
        3. Three CustomUsers with id in (10, 20, 30) and is_tutor=True
        4. Same as the above
        5. n CustomUsers that teach student with id=1

        If multiple GET params are specified, it will be evaluated in the
        order mentioned above
        """
        url_query = request.GET

        if not url_query:
            return self.get_all_tutors()

        tutor_ids = url_query.getlist("tutor_ids")
        student_id = url_query.get("student_id")

        if tutor_ids:
            return self.get_tutors_by_ids(tutor_ids)
        if student_id:
            return self.get_tutors_of_student(student_id)

        return Response(
            {"error": "No student or tutor ids provided"},
            status=status.HTTP_400_BAD_REQUEST,
        )


class AddTutorStudentRelationshipView(views.APIView):
    permission_classes = [IsManager | IsTutor]

    def add_teaches_relation(self, tutor_id: int, student_ids: list[int]):
        # No point in adding if tutor ID is invalid
        if not isinstance(tutor_id, int):
            return [], []

        success = []  # students successfully added
        errors = []  # students not successfully added
        for s_id in student_ids:
            # Skip invalid parameter values
            if not isinstance(s_id, int):
                continue

            ok, error_msg = Teaches.objects.add_teaching_relationship(tutor_id, s_id)
            if ok:
                success.append([tutor_id, s_id])
            else:
                errors.append({"pair": [tutor_id, s_id], "reason": error_msg})
        return success, errors

    def post(self, request: HttpRequest):
        """
        Example payload for managers
        [
            {"tutor_id": 10, "student_ids": [1, 2, 3]},
            {"tutor_id": 11, "student_ids": [4, 5, 6]},
            {"tutor_id": 12, "student_ids": [1, 3, 5]}
        ]

        Example payload for tutors
        {
            "student_ids": [1, 2, 3]
        }
        """
        payload = request.data
        if request.user.is_tutor:
            payload["tutor_id"] = request.user.id

        if not isinstance(payload, list):
            payload = [payload]

        # Payload sanity check
        for teaches in payload:
            if (
                not isinstance(teaches, dict)
                or "tutor_id" not in teaches
                or not isinstance(teaches["tutor_id"], int)
                or "student_ids" not in teaches
                or not isinstance(teaches["student_ids"], list)
                or not all(isinstance(s_id, int) for s_id in teaches["student_ids"])
            ):
                return Response(
                    {"error": "Payload in wrong format"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        success = []  # students successfully added
        errors = []  # students not successfully added
        for teaches in payload:
            # Add teaches relation and update response messages
            tutor_id = teaches["tutor_id"]
            student_ids = teaches["student_ids"]
            scs, errs = self.add_teaches_relation(tutor_id, student_ids)
            success.extend(scs)
            errors.extend(errs)

        response = {}
        if success:
            response["success"] = success
        if errors:
            response["error"] = errors

        return Response(response, status=status.HTTP_200_OK)


class UpdateUserInfoView(generics.UpdateAPIView):
    permission_classes = [IsStudent | IsTutor]
    serializer = UpdateUserInfoSerializer

    def patch(self, request, partial=True):
        serializer = self.serializer(request.user, request.data, partial=partial)
        try:
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return Response(data=serializer.data, status=status.HTTP_200_OK)
        except serializers.ValidationError as e:
            return Response(
                data={"message": e.detail}, status=status.HTTP_400_BAD_REQUEST
            )
