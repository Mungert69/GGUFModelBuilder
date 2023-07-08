using NetworkMonitor.Objects;
using NetworkMonitor.Connection;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Linq;
using Xunit;
using MetroLog;

namespace NetworkMonitor.Tests
{
    public class QuantumConnectTests
    {
        private MonitorPingInfo pingInfo=new MonitorPingInfo();
        private PingParams pingParams;
        private string csvFilePath = "/home/mahadeva/code/NetworkMonitorProcessor/AlgoTable-test.csv";
         private static ILogger _logger = LogManagerFactory.DefaultLogManager.GetLogger<QuantumConnectTests>();

        public QuantumConnectTests()
        {
            
            pingParams = new PingParams
            {
                Timeout = 10000
            };
        }

        [Fact]
        public async void TestConnectWithQuantumSafeEncryption()
        {
            var monitorPingInfo = new MonitorPingInfo
            {
                MonitorIPID = 1,
                Address = "pq.cloudflareresearch.com",
                EndPointType = "Quantum",
                PingInfos = new List<PingInfo>(),
                Timeout = 5000
            };
          
          string oqsProviderPath="/usr/local/lib/";

               List<AlgorithmInfo> algorithmInfoList = CsvParser.ParseCsv(csvFilePath);
            // Arrange
            var quantumConnect = new QuantumConnect( algorithmInfoList, oqsProviderPath,_logger);
              //quantumConnect.PingParams=pingParams;
                        quantumConnect.MpiStatic=new MPIStatic(pingInfo);
            // Act
            await quantumConnect.Connect();

            // Assert
            Assert.Equal(1, monitorPingInfo.PacketsSent);
            Assert.Contains("Using quantum safe handshake", monitorPingInfo.Status);
            Assert.Single(monitorPingInfo.PingInfos);
            Assert.Equal("Success", monitorPingInfo.PingInfos.ToList()[0].Status);
            }

        [Fact]
        public async void TestConnectWithNotQuantumSafeEncryption()
        {
            // Arrange
              string oqsProviderPath="/usr/local/lib/";
               List<AlgorithmInfo> algorithmInfoList = CsvParser.ParseCsv(csvFilePath);
     
            var pingInfo = new MonitorPingInfo
            {
                MonitorIPID = 1,
                Address = "srv1.mahadeva.co.uk",
                Port = 4433,
                EndPointType = "Quantum",
                PingInfos = new List<PingInfo>(),
                Timeout = 5000
            };
            var quantumConnect = new QuantumConnect(algorithmInfoList, oqsProviderPath,_logger);
             // quantumConnect.PingParams=pingParams;
            quantumConnect.MpiStatic=new MPIStatic(pingInfo);

            // Act
            await quantumConnect.Connect();

            // Assert
            Assert.Equal(1, pingInfo.PacketsSent);
            Assert.Contains("Could not negotiate quantum safe handshake", pingInfo.Status);
            Assert.Single(pingInfo.PingInfos);
            Assert.Contains("Could not negotiate quantum safe handshake", pingInfo.PingInfos.ToList()[0].Status);
           
        }

    }
}