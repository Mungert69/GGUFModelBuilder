using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Net.NetworkInformation;
using System.Net;
using System.Threading.Tasks;
using System.Net.Sockets;
using System.Linq;
using NetworkMonitor.Objects;
using Microsoft.Extensions.Logging;

namespace NetworkMonitor.Processor.Services;
public class ScanProcessor
{
    LocalScanProcessorStates _scanProcessorStates;
    private ILogger _logger;
    public ScanProcessor(ILogger logger,LocalScanProcessorStates scanProcessorStates)
    {
        _logger = logger;
        _scanProcessorStates = scanProcessorStates;
        _scanProcessorStates.OnStartScanAsync += Scan;

    }
    public void Dispose()
    {
        _scanProcessorStates.OnStartScanAsync -= Scan;
    }

    public async Task Scan(string endPointType)
    {
        var (localIP, subnetMask) = GetLocalIPAddressAndSubnetMask();
        var (networkAddress, startIP, endIP) = GetNetworkRange(localIP, subnetMask);
        int timeout = 1000; // Ping timeout in milliseconds


        _logger.LogInformation($"Pinging range: {IntToIp(networkAddress + startIP)} - {IntToIp(networkAddress + endIP)}");

        List<Task> pingTasks = new List<Task>();
        for (int i = startIP; i <= endIP; i++)
        {
            string ip = IntToIp(networkAddress + i);
            pingTasks.Add(PingAndResolveAsync(ip, timeout, _scanProcessorStates.ActiveDevices, _scanProcessorStates.PingInfos));
        }

        await Task.WhenAll(pingTasks);

        _logger.LogInformation("Devices up in the network:");
        foreach (var device in _scanProcessorStates.ActiveDevices)
        {
            _logger.LogInformation($"IP Address: {device.Address}, Hostname: {device.MessageForUser}");
        }

        _logger.LogInformation("Ping Information:");
        foreach (var pingInfo in _scanProcessorStates.PingInfos)
        {
            _logger.LogInformation($"IP: {pingInfo.MonitorPingInfoID}, Status: {pingInfo.Status}, Time: {pingInfo.RoundTripTime}ms");
        }
    }

    public (string, string) GetLocalIPAddressAndSubnetMask()
    {
        _logger.LogInformation("Searching for appropriate network interface...");

        foreach (NetworkInterface ni in NetworkInterface.GetAllNetworkInterfaces())
        {
            _logger.LogInformation($"Checking interface: {ni.Name}, Type: {ni.NetworkInterfaceType}, OperationalStatus: {ni.OperationalStatus}");

            if (ni.OperationalStatus != OperationalStatus.Up ||
                ni.NetworkInterfaceType == NetworkInterfaceType.Loopback ||
                ni.Description.IndexOf("virtual", StringComparison.OrdinalIgnoreCase) >= 0 ||
                ni.NetworkInterfaceType == NetworkInterfaceType.Tunnel)
            {
                _logger.LogInformation("Skipping this interface.");
                continue;
            }

            // Prioritize Ethernet and Wireless interfaces
            if (ni.NetworkInterfaceType != NetworkInterfaceType.Ethernet &&
                ni.NetworkInterfaceType != NetworkInterfaceType.Wireless80211)
            {
                _logger.LogInformation("Not an Ethernet or Wi-Fi interface, will use only if no better option found.");
                continue;
            }

            var ipProperties = ni.GetIPProperties();

            // Check for default gateway
            if (!ipProperties.GatewayAddresses.Any())
            {
                _logger.LogInformation("No default gateway found, skipping.");
                continue;
            }

            foreach (UnicastIPAddressInformation ip in ipProperties.UnicastAddresses)
            {
                if (ip.Address.AddressFamily == AddressFamily.InterNetwork &&
                    !IPAddress.IsLoopback(ip.Address))
                {
                    _logger.LogInformation($"Selected IP: {ip.Address}, Subnet Mask: {ip.IPv4Mask}");
                    return (ip.Address.ToString(), ip.IPv4Mask.ToString());
                }
            }
        }

        throw new Exception("No suitable local IP Address and Subnet Mask found!");
    }
    public (int networkAddress, int startIP, int endIP) GetNetworkRange(string ipAddress, string subnetMask)
    {
        int ipInt = IpToInt(ipAddress);
        int maskInt = IpToInt(subnetMask);

        int networkAddress = ipInt & maskInt;
        int broadcastAddress = networkAddress | ~maskInt;

        int startIP = 1; // Network address + 1
        int endIP = broadcastAddress - networkAddress - 1; // Broadcast address - network address - 1

        return (networkAddress, startIP, endIP);
    }

    public int IpToInt(string ipAddress)
    {
        return BitConverter.ToInt32(IPAddress.Parse(ipAddress).GetAddressBytes().Reverse().ToArray(), 0);
    }

    public string IntToIp(int ipInt)
    {
        return new IPAddress(BitConverter.GetBytes(ipInt).Reverse().ToArray()).ToString();
    }

    public async Task PingAndResolveAsync(string ip, int timeout, ConcurrentBag<MonitorIP> activeDevices, ConcurrentBag<PingInfo> pingInfos)
    {
        using (Ping ping = new Ping())
        {
            try
            {
                PingReply reply = await ping.SendPingAsync(ip, timeout);
                var pingInfo = new PingInfo
                {
                    MonitorPingInfoID = IpToInt(ip),
                    DateSent = DateTime.UtcNow,
                    Status = reply.Status.ToString(),
                    RoundTripTime = (ushort?)reply.RoundtripTime
                };

                if (reply.Status == IPStatus.Success)
                {
                    string hostname = ResolveHostName(ip);

                    var monitorIP = new MonitorIP
                    {
                        Address = ip,
                        MessageForUser = hostname
                    };
                    activeDevices.Add(monitorIP);
                }

                pingInfos.Add(pingInfo);
            }
            catch (Exception ex)
            {
                var pingInfo = new PingInfo
                {
                    MonitorPingInfoID = IpToInt(ip),
                    DateSent = DateTime.UtcNow,
                    Status = $"Error: {ex.Message}",
                    RoundTripTime = 0
                };
                pingInfos.Add(pingInfo);
            }
        }
    }

    public string ResolveHostName(string ipAddress)
    {
        try
        {
            IPHostEntry entry = Dns.GetHostEntry(ipAddress);
            return entry.HostName;
        }
        catch (Exception)
        {
            return "N/A";
        }
    }
}
