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
using NetworkMonitor.Utils;
using System.Threading;

namespace NetworkMonitor.Processor.Services;
 public interface ICmdProcessor : IDisposable
    {
        Task Scan();
    Task<string> RunCommand(string arguments, CancellationToken cancellationToken, ProcessorScanDataObj? processorScanDataObj = null);
        bool UseDefaultEndpoint { get; set; }
    }
public class ScanCmdProcessor : ICmdProcessor
{
    private LocalCmdProcessorStates _scanProcessorStates;
    private IRabbitRepo _rabbitRepo;
    private NetConnectConfig _netConfig;
    private ILogger _logger;
    
    public ScanCmdProcessor(ILogger logger, LocalCmdProcessorStates cmdProcessorStates, IRabbitRepo rabbitRepo, NetConnectConfig netConfig)
    {
        _logger = logger;
        _scanProcessorStates = cmdProcessorStates;
        _rabbitRepo = rabbitRepo;
        _netConfig = netConfig;
        _scanProcessorStates.OnStartScanAsync += Scan;

    }

    public bool UseDefaultEndpoint { get => _scanProcessorStates.UseDefaultEndpointType; set => _scanProcessorStates.UseDefaultEndpointType = value; }

    public void Dispose()
    {
        _scanProcessorStates.OnStartScanAsync -= Scan;
    }

    public async Task Scan()
    {
        string message = "";
        try
        {
            _scanProcessorStates.IsRunning = true;
            var (localIP, subnetMask, cidr) = NetworkUtils.GetLocalIPAddressAndSubnetMask(_logger, _scanProcessorStates);
            var (networkAddress, startIP, endIP) = NetworkUtils.GetNetworkRange(localIP, subnetMask);
            int timeout = 1000; // Ping timeout in milliseconds

            message = $"Pinging range: {NetworkUtils.IntToIp(networkAddress + startIP)} - {NetworkUtils.IntToIp(networkAddress + endIP)}\n";
            _logger.LogInformation(message);
            _scanProcessorStates.RunningMessage += message;

            List<Task> pingTasks = new List<Task>();
            for (int i = startIP; i <= endIP; i++)
            {
                string ip = NetworkUtils.IntToIp(networkAddress + i);
                pingTasks.Add(PingAndResolveAsync(ip, timeout, _scanProcessorStates.ActiveDevices, _scanProcessorStates.PingInfos));
            }

            await Task.WhenAll(pingTasks);
            message = "\n Found devices up in the network:\n";
            _logger.LogInformation(message);
            _scanProcessorStates.RunningMessage += message;

            _scanProcessorStates.IsSuccess = true;
            var monitorIPs = _scanProcessorStates.ActiveDevices.ToList();
            foreach (var monitorIP in monitorIPs)
            {
                monitorIP.AppID = _netConfig.AppID;
                monitorIP.UserID = _netConfig.Owner;
                monitorIP.Timeout = 59000;
                monitorIP.AgentLocation = _netConfig.MonitorLocation;
                monitorIP.DateAdded = DateTime.UtcNow;
                monitorIP.Enabled = true;
                monitorIP.EndPointType = _scanProcessorStates.DefaultEndpointType;
                monitorIP.Hidden = false;
                monitorIP.Port = 0;
                message = $"IP Address: {monitorIP.Address}, Hostname: {monitorIP.MessageForUser}\n";
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
            processorDataObj.MonitorIPs = monitorIPs;
            await _rabbitRepo.PublishAsync<ProcessorDataObj>("saveMonitorIPs", processorDataObj);
            message = $"\nSent {monitorIPs.Count} hosts to Free Network Monitor Service. Please wait 2 mins for hosts to become live. You can view the in the Host Data menu or visit https://freenetworkmonitor.click/dashboard and login using the same email address you registered your agent with.\n";
            _logger.LogInformation(message);
            _scanProcessorStates.RunningMessage += message;
        }
        catch (Exception e)
        {
            message = $" Error : Failed to scan for local hosts. Error was :{e.Message}\n";
            _logger.LogError(message);
            _scanProcessorStates.CompletedMessage += message;
            _scanProcessorStates.IsSuccess = false;
        }
        finally
        {
            _scanProcessorStates.IsRunning = false;
        }

    }


    private async Task PingAndResolveAsync(string ip, int timeout, ConcurrentBag<MonitorIP> activeDevices, ConcurrentBag<PingInfo> pingInfos)
    {
        using (Ping ping = new Ping())
        {
            try
            {
                PingReply reply = await ping.SendPingAsync(ip, timeout);
                var pingInfo = new PingInfo
                {
                    MonitorPingInfoID = NetworkUtils.IpToInt(ip),
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
                    MonitorPingInfoID = NetworkUtils.IpToInt(ip),
                    DateSent = DateTime.UtcNow,
                    Status = $"Error: {ex.Message}",
                    RoundTripTime = 0
                };
                pingInfos.Add(pingInfo);
            }
        }
    }

   public async Task<string> RunCommand(string arguments, CancellationToken cancellationToken, ProcessorScanDataObj? processorScanDataObj = null)
{
    throw new NotImplementedException();
}


    private string ResolveHostName(string ipAddress)
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
