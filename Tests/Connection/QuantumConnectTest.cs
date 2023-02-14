using NetworkMonitor.Objects;
using NetworkMonitor.Connection;
using System.Collections.Generic;
using Xunit;

namespace NetworkMonitor.Tests
{
    public class QuantumConnectTests
    {
        private MonitorPingInfo pingInfo;
        private PingParams pingParams;

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
            var pingInfo = new MonitorPingInfo
            {
                MonitorIPID = 1,
                Address = "https://www.google.com",
                EndPointType = "Quantum",
                PingInfos = new List<PingInfo>(),
                Timeout = 5000
            };
            // Arrange
            var quantumConnect = new QuantumConnect(pingInfo, pingParams);

            // Act
            await quantumConnect.connect();

            // Assert
            Assert.Equal(1, pingInfo.PacketsSent);
            Assert.Equal("Using quantum safe encryption", pingInfo.Status);
            Assert.Single(pingInfo.PingInfos);
            Assert.Equal("Success", pingInfo.PingInfos[0].Status);
            }

        [Fact]
        public async void TestConnectWithNotQuantumSafeEncryption()
        {
            // Arrange
            var pingInfo = new MonitorPingInfo
            {
                MonitorIPID = 1,
                Address = "https://basic.com",
                EndPointType = "Quantum",
                PingInfos = new List<PingInfo>(),
                Timeout = 5000
            };
            var quantumConnect = new QuantumConnect(pingInfo, pingParams);
         

            // Act
            await quantumConnect.connect();

            // Assert
            Assert.Equal(1, pingInfo.PacketsSent);
            Assert.Equal("Not using quantum safe encryption", pingInfo.Status);
            Assert.Single(pingInfo.PingInfos);
            Assert.Equal("Not using quantum safe encryption", pingInfo.PingInfos[0].Status);
           
        }

    }
}