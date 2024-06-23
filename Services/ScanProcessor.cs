using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Net.NetworkInformation;
using System.Net;
using System.Threading.Tasks;
using System.Net.Sockets;
using System.Linq;
using NetworkMonitor.Objects;
using NetworkMonitor.Objects.Repository;
using Microsoft.Extensions.Logging;
using NetworkMonitor.Objects.ServiceMessage;
using NetworkMonitor.Connection;

namespace NetworkMonitor.Processor.Services;
public class ScanProcessor
{
    private LocalScanProcessorStates _scanProcessorStates;
    private IRabbitRepo _rabbitRepo;
    private NetConnectConfig _netConfig;
    private ILogger _logger;
    public ScanProcessor(ILogger logger,LocalScanProcessorStates scanProcessorStates, IRabbitRepo rabbitRepo, NetConnectConfig netConfig)
    {
        _logger = logger;
        _scanProcessorStates = scanProcessorStates;
        _rabbitRepo = rabbitRepo;
                    _netConfig = netConfig;
        _scanProcessorStates.OnStartScanAsync += Scan;

    }
    public void Dispose()
    {
        _scanProcessorStates.OnStartScanAsync -= Scan;
    }

    public async Task Scan(string endPointType)
    {
        string message = "";
        try
        {
            _scanProcessorStates.IsRunning = true;
            var (localIP, subnetMask) = GetLocalIPAddressAndSubnetMask();
            var (networkAddress, startIP, endIP) = GetNetworkRange(localIP, subnetMask);
            int timeout = 1000; // Ping timeout in milliseconds

            message = $"Pinging range: {IntToIp(networkAddress + startIP)} - {IntToIp(networkAddress + endIP)}\n";
            _logger.LogInformation(message);
            _scanProcessorStates.RunningMessage += message;

            List<Task> pingTasks = new List<Task>();
            for (int i = startIP; i <= endIP; i++)
            {
                string ip = IntToIp(networkAddress + i);
                pingTasks.Add(PingAndResolveAsync(ip, timeout, _scanProcessorStates.ActiveDevices, _scanProcessorStates.PingInfos));
            }

            await Task.WhenAll(pingTasks);
            message = "\n Found devices up in the network:\n";
            _logger.LogInformation(message);
            _scanProcessorStates.RunningMessage += message;

            _scanProcessorStates.IsSuccess = true;
            foreach (var device in _scanProcessorStates.ActiveDevices)
            {
                device.AppID = _netConfig.AppID;
                device.UserID = _netConfig.Owner;
                device.Timeout=59000;
                device.AgentLocation=_netConfig.MonitorLocation;
                device.DateAdded = DateTime.UtcNow;
                device.Enabled = true;
                device.EndPointType = "icmp";
                device.Hidden = false;
                device.Port=0;
                message = $"IP Address: {device.Address}, Hostname: {device.MessageForUser}\n";
                _scanProcessorStates.CompletedMessage += message;
                _logger.LogInformation(message);
            }

            _logger.LogInformation("Ping Information:");
            foreach (var pingInfo in _scanProcessorStates.PingInfos)
            {
                _logger.LogInformation($"IP: {pingInfo.MonitorPingInfoID}, Status: {pingInfo.Status}, Time: {pingInfo.RoundTripTime}ms");
            }
            var processorDataObj = new ProcessorDataObj();
            processorDataObj.AppID = _netConfig.AppID;
            processorDataObj.AuthKey = _netConfig.AuthKey;
            processorDataObj.RabbitPassword = _netConfig.LocalSystemUrl.RabbitPassword;
            await _rabbitRepo.PublishAsync<ProcessorDataObj>("saveMonitorIPs",processorDataObj);
        }
        catch (Exception e)
        {
            message = $" Error : Failed to scan for local hosts. Error was :{e.Message}\n";
            _logger.LogError(message);
            _scanProcessorStates.CompletedMessage += message;
            _scanProcessorStates.IsSuccess = false;
        }
        finally { 
              _scanProcessorStates.IsRunning = false;
        }
       
    }

    public (string, string) GetLocalIPAddressAndSubnetMask()
    {
        var message = "Searching for appropriate network interface...\n";
        _logger.LogInformation(message);
        _scanProcessorStates.RunningMessage += message;

        foreach (NetworkInterface ni in NetworkInterface.GetAllNetworkInterfaces())
        {
            message=$"Checking interface: {ni.Name}, Type: {ni.NetworkInterfaceType}, OperationalStatus: {ni.OperationalStatus}\n";
 _logger.LogInformation(message);
        _scanProcessorStates.RunningMessage += message;
            if (ni.OperationalStatus != OperationalStatus.Up ||
                ni.NetworkInterfaceType == NetworkInterfaceType.Loopback ||
                ni.Description.IndexOf("virtual", StringComparison.OrdinalIgnoreCase) >= 0 ||
                ni.NetworkInterfaceType == NetworkInterfaceType.Tunnel)
            {
                message="Skipping this interface.\n";
                 _logger.LogInformation(message);
        _scanProcessorStates.RunningMessage += message;
                continue;
            }

            // Prioritize Ethernet and Wireless interfaces
            if (ni.NetworkInterfaceType != NetworkInterfaceType.Ethernet &&
                ni.NetworkInterfaceType != NetworkInterfaceType.Wireless80211)
            {
                message= "Not an Ethernet or Wi-Fi interface, will use only if no better option found.\n";
                 _logger.LogInformation(message);
        _scanProcessorStates.RunningMessage += message;
                continue;
            }

            var ipProperties = ni.GetIPProperties();

            // Check for default gateway
            if (!ipProperties.GatewayAddresses.Any())
            {
                message= "No default gateway found, skipping.\n";
                 _logger.LogInformation(message);
        _scanProcessorStates.RunningMessage += message;
                continue;
            }

            foreach (UnicastIPAddressInformation ip in ipProperties.UnicastAddresses)
            {
                if (ip.Address.AddressFamily == AddressFamily.InterNetwork &&
                    !IPAddress.IsLoopback(ip.Address))
                {
                    message=$"Selected IP: {ip.Address}, Subnet Mask: {ip.IPv4Mask}\n";
                     _logger.LogInformation(message);
        _scanProcessorStates.RunningMessage += message;
                    return (ip.Address.ToString(), ip.IPv4Mask.ToString());
                }
            }
        }

        throw new Exception("No suitable local IP Address and Subnet Mask found!\n");
        
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
