from database import initialize_database, get_session


def main():
    print("Initializing database...")

    initialize_database()

    session = get_session()

    print("Database initialized successfully.")

    session.close()


if __name__ == "__main__":
    main()