# Build stage
FROM mcr.microsoft.com/dotnet/sdk:8.0 AS build
WORKDIR /source
COPY . ./

RUN dotnet restore NetworkMonitorProcessor.csproj -r linux-x64




# Ensure all files, including openssl, are copied during publish
RUN dotnet publish NetworkMonitorProcessor.csproj -c release -o /app -r linux-x64 --self-contained false

# Runtime stage
FROM mcr.microsoft.com/dotnet/aspnet:8.0
WORKDIR /app

# Install any necessary dependencies (e.g., nmap, vim)
RUN apt-get update && apt-get upgrade -y && apt-get install -y apt-utils vim

# Copy published files from build stage
COPY --from=build /app ./
COPY appsettings.json ./appsettings.json

# Set entry point for the application
ENTRYPOINT ["dotnet", "./NetworkMonitorProcessor.dll"]

