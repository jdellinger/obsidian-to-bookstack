# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

ENV HOME=/app

# Copy the entire project to the working directory
COPY . .

# Install the project and its dependencies from pyproject.toml
RUN pip install .

# Set the entrypoint to the application's command-line script
ENTRYPOINT ["obsidian_to_bookstack"]

# By default, show the help message if no command is provided
CMD ["--help"]
