from django.contrib.auth.base_user import BaseUserManager


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("邮箱不能为空")
        email = self.normalize_email(email).lower()
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        extra_fields.setdefault("membership_level", "L1")
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("membership_level", "L3")

        if extra_fields.get("is_staff") is not True:
            raise ValueError("超级用户必须设置 is_staff=True")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("超级用户必须设置 is_superuser=True")
        if extra_fields.get("membership_level") != "L3":
            raise ValueError("超级用户必须是 L3")

        return self._create_user(email, password, **extra_fields)
