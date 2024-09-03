using System.Threading;
using System.Threading.Tasks;
using System;
namespace NetworkMonitor.Processor.Services;
public class CommandTask
{
    public string MessageId { get; }
    public Func<Task> TaskFunc { get; }
    public bool IsRunning { get; set; }
    public bool IsSuccessful { get; set; }
    public CancellationTokenSource CancellationTokenSource { get; }

    public CommandTask(string messageId, Func<Task> taskFunc, CancellationTokenSource cancellationTokenSource)
    {
        MessageId = messageId;
        TaskFunc = taskFunc;
        CancellationTokenSource = cancellationTokenSource;
        IsRunning = true;
        IsSuccessful = false;
    }
}
