using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Logging;
using NetworkMonitor.Objects;
using NetworkMonitor.Objects.ServiceMessage;
using NetworkMonitorProcessor.Services;
using System;
using System.Collections.Generic;
using Dapr;

namespace NetworkMonitorProcessor.Controllers
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
                _monitorPingProcessor.UpdateAlertFlag(monitorPingInfoIds, true);
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

       // [Topic("pubsub", "processorAlertSent")]
        [HttpPost("alertsent")]
        [Consumes("application/json")]
        public ActionResult<ResultObj> AlertSent([FromBody] List<int> monitorPingInfoIds)
        {
            ResultObj result = new ResultObj();
            result.Success = false;
            result.Message = "MessageAPI : ProcessorAlertSent : ";

            try
            {
                _monitorPingProcessor.UpdateAlertSent(monitorPingInfoIds, true);
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

        //[Topic("pubsub", "processorResetAlert")]
        [HttpPost("resetalert")]
        [Consumes("application/json")]
        public ActionResult<ResultObj> ResetAlert([FromBody] List<int> monitorPingInfoIds)
        {
            ResultObj result = new ResultObj();
            result.Success = false;
            result.Message = "MessageAPI : ProcessorResetAlert : ";

            try
            {
                _monitorPingProcessor.ResetAlert(monitorPingInfoIds[0]);
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
