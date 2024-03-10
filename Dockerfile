FROM mungert/riscv64-net8:latest AS build-env
WORKDIR /App

# Copy everything
COPY ./NetworkMonitorProcessor ./
COPY ./NetworkMonitor ./
# Restore as distinct layers
RUN /usr/share/dotnet/dotnet restore NetworkMonitorProcessor-Risc.csproj
# Build and publish a release
RUN /usr/share/dotnet/dotnet publish NetworkMonitorProcessor-Risc.csproj -c Release -o out

## Build runtime image
#FROM mungert/riscv64-net8:latest
WORKDIR /App
COPY --from=build-env /App/out .
ENTRYPOINT ["dotnet", "NetworkMonitorProcessor.dll"]
