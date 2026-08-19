import getpass

from services.auth_service import hash_password


def main() -> None:
    password = getpass.getpass("New Vera password: ")
    confirmation = getpass.getpass("Confirm password: ")
    if password != confirmation:
        raise SystemExit("Passwords do not match.")
    print(hash_password(password))


if __name__ == "__main__":
    main()
