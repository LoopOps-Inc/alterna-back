from setuptools import setup, find_packages

setup(
    name="altm-backend",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "fastapi>=0.110.0",
        "uvicorn>=0.28.0",
        "pydantic[email]>=2.6.0",
        "pydantic-settings>=2.2.0",
        "sqlalchemy>=2.0.0",
        "psycopg2-binary>=2.9.0",
        "redis>=5.0.0",
        "argon2-cffi>=23.1.0",
        "pyjwt>=2.8.0",
        "cryptography>=42.0.0",
        "httpx>=0.27.0"
    ]
)
