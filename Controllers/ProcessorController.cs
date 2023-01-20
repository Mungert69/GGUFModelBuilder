using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Logging;
using NetworkMonitor.Objects;
using NetworkMonitor.Objects.ServiceMessage;
using NetworkMonitor.Processor.Services;
using System;
using System.Collections.Generic;
using System.Linq;
using Dapr;
namespace NetworkMonitor.Processor.Controllers
{
    [ApiController]
    [Route("[controller]")]
    public class ProcessorController : ControllerBase
    {
        private readonly ILogger<ProcessorController> _logger;
        private IMonitorPingProcessor _monitorPingProcessor;
        public ProcessorController(ILogger<ProcessorController> logger, IMonitorPingProcessor monitorPingProcessor)
        {
            _logger = logger;
            _monitorPingProcessor = monitorPingProcessor;
        }
        // [Topic("pubsub", "processorConnect"),]
        //[TopicMetadata( "ttlInSeconds", "60")]
        [HttpPost("connect")]
        public ActionResult<ResultObj> Connect(ProcessorConnectObj connectObj)
        {
            ResultObj result = new ResultObj();
            result.Success = false;
            result.Message = "MessageAPI : ProcessorConnect : ";
            try
            {
                ResultObj connectResult = _monitorPingProcessor.Connect(connectObj);
                result.Message += connectResult.Message;
                result.Success = connectResult.Success;
                result.Data = connectResult.Data;
                _logger.LogInformation(result.Message);
            }
            catch (Exception e)
            {
                result.Data = null;
                result.Success = false;
                result.Message += "Error : Failed to run Connect : Error was : " + e.ToString() + " ";
                _logger.LogError(result.Message);
            }
            return result;
        }
        [HttpPost("removePingInfos")]
        public ActionResult<ResultObj> RemovePingInfos(List<RemovePingInfo> removePingInfos)
        {
            ResultObj result = new ResultObj();
            result.Success = false;
            result.Message = "MessageAPI : RemovePingInfos : ";
            try
            {
                _monitorPingProcessor.AddRemovePingInfos(removePingInfos);
                result.Message += "Success : updated RemovePingInfos. ";
                result.Success = true;
                _logger.LogInformation(result.Message);
            }
            catch (Exception e)
            {
                result.Success = false;
                result.Message += "Error : Failed to remove PingInfos: Error was : " + e.Message + " ";
                _logger.LogError(result.Message);
            }
            return result;
        }
        //[Topic("pubsub", "processorInit")]
        [HttpPost("init")]
        [Consumes("application/json")]
        public ActionResult<ResultObj> Init([FromBody] ProcessorInitObj initObj)
        {
            ResultObj result = new ResultObj();
            result.Success = false;
            result.Message = "MessageAPI : ProcessorInit : ";
            try
            {
                _monitorPingProcessor.init(initObj);
                result.Message += "Success ran ok ";
                result.Success = true;
                _logger.LogInformation(result.Message);
            }
            catch (Exception e)
            {
                result.Data = null;
                result.Success = false;
                result.Message += "Error : Failed to receive message : Error was : " + e.Message + " ";
                _logger.LogError(result.Message);
            }
            return result;
        }
        // [Topic("pubsub", "processorAlertFlag")]
        [HttpPost("alertflag")]
        [Consumes("application/json")]
        public ActionResult<ResultObj> AlertFlag([FromBody] List<int> monitorPingInfoIds)
        {
            ResultObj result = new ResultObj();
            result.Success = false;
            result.Message = "MessageAPI : ProcessorAlertFlag : ";
            try
            {
                monitorPingInfoIds.ForEach(f => _logger.LogDebug("ProcessorAlertFlag Found MonitorPingInfo ID=" + f));
                List<ResultObj> results = _monitorPingProcessor.UpdateAlertFlag(monitorPingInfoIds, true);
                result.Success = results.Where(w => w.Success == false).ToList().Count() == 0;
                if (result.Success) result.Message += "Success ran ok ";
                else
                {
                    results.Select(s => s.Message).ToList().ForEach(f => result.Message += f);
                    result.Data = results;
                }
                _logger.LogInformation(result.Message);
            }
            catch (Exception e)
            {
                result.Data = null;
                result.Success = false;
                result.Message += "Error : Failed to receive message : Error was : " + e.Message + " ";
                _logger.LogError(result.Message);
            }
            return result;
        }
        // [Topic("pubsub", "processorAlertSent")]
        [HttpPost("alertsent")]
        [Consumes("application/json")]
        public ActionResult<ResultObj> AlertSent([FromBody] List<int> monitorIPIDs)
        {
            ResultObj result = new ResultObj();
            result.Success = false;
            result.Message = "MessageAPI : ProcessorAlertSent : ";
            try
            {
                monitorIPIDs.ForEach(f => _logger.LogDebug("ProcessorSentFlag Found monitorIPID =" + f));
                List<ResultObj> results = _monitorPingProcessor.UpdateAlertSent(monitorIPIDs, true);
                result.Success = results.Where(w => w.Success == false).ToList().Count() == 0;
                if (result.Success) result.Message += "Success ran ok ";
                else
                {
                    results.Select(s => s.Message).ToList().ForEach(f => result.Message += f);
                    result.Data = results;
                }
                _logger.LogInformation(result.Message);
            }
            catch (Exception e)
            {
                result.Data = null;
                result.Success = false;
                result.Message += "Error : Failed to receive message : Error was : " + e.Message + " ";
                _logger.LogError(result.Message);
            }
            return result;
        }
        //[Topic("pubsub", "processorResetAlerts")]
        [HttpPost("ProcessorResetAlerts")]
        [Consumes("application/json")]
        public ActionResult<ResultObj> ResetAlerts([FromBody] List<int> monitorIPIDs)
        {
            ResultObj result = new ResultObj();
            result.Success = false;
            result.Message = "MessageAPI : ProcessorResetAlerts : ";
            try
            {
                var results= _monitorPingProcessor.ResetAlerts(monitorIPIDs);
                results.ForEach(f => result.Message+=f.Message);
                result.Success= results.All(a => a.Success==true) && results.Count()!=0;
                result.Data =results;
                _logger.LogInformation(result.Message);
            }
            catch (Exception e)
            {
                result.Data = null;
                result.Success = false;
                result.Message += "Error : Failed to receive message : Error was : " + e.Message + " ";
                _logger.LogError(result.Message);
            }
            return result;
        }
        //[Topic("pubsub", "processorQueueDic")]
        [HttpPost("queuedic")]
        [Consumes("application/json")]
        public ActionResult<ResultObj> QueueDic([FromBody] ProcessorQueueDicObj queueDicObj)
        {
            ResultObj result = new ResultObj();
            result.Success = false;
            result.Message = "MessageAPI : ProcessorQueueDic : ";
            try
            {
                _monitorPingProcessor.AddMonitorIPsToQueueDic(queueDicObj);
                result.Message += "Success ran ok ";
                result.Success = true;
                _logger.LogInformation(result.Message);
            }
            catch (Exception e)
            {
                result.Data = null;
                result.Success = false;
                result.Message += "Error : Failed to receive message : Error was : " + e.Message + " ";
                _logger.LogError(result.Message);
            }
            return result;
        }
        //[Topic("pubsub", "processorWakeUp")]
        [HttpPost("wakeup")]
        public ActionResult<ResultObj> WakeUp()
        {
            ResultObj result = new ResultObj();
            result.Success = false;
            result.Message = "MessageAPI : WakeUp : ";
            try
            {
                _monitorPingProcessor.Awake = true;
                result.Message += "Success ran WakeUp ok ";
                result.Success = true;
                _logger.LogInformation(result.Message);
            }
            catch (Exception e)
            {
                result.Data = null;
                result.Success = false;
                result.Message += "Error : Failed to receive message : Error was : " + e.Message + " ";
                _logger.LogError(result.Message);
            }
            return result;
        }
    }
}
