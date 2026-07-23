# CPU Scheduling

The scheduler decides which of the ready processes gets the CPU next.
Different algorithms optimize for different things — throughput, average
waiting time, response time, fairness — and no single algorithm is best on
every metric simultaneously, which is why real operating systems (Linux's
Completely Fair Scheduler, for instance) use hybrids rather than a textbook
algorithm directly.

## First-Come, First-Served (FCFS)

Processes are scheduled in the order they arrive, non-preemptively — once a
process starts running, it runs to completion. Simple to implement, but
suffers from the convoy effect: a single long process at the front of the
queue makes every process behind it wait, dragging down average waiting
time even if most of those processes are individually short.

## Shortest Job First (SJF)

Schedules the process with the shortest next CPU burst. This is provably
optimal for minimizing average waiting time among non-preemptive algorithms,
but requires knowing burst lengths in advance, which is generally not
possible in a real system — in practice, SJF is approximated by predicting
the next burst from a process's recent history (an exponentially weighted
average of past bursts). SJF can also starve long processes indefinitely if
short processes keep arriving.

The preemptive version, Shortest Remaining Time First (SRTF), can interrupt
a running process if a new process arrives with a shorter remaining burst
than the current process has left.

## Round Robin

Each process gets a fixed time quantum; when its quantum expires, it's
preempted and moved to the back of the ready queue. Round Robin is designed
for fairness and responsiveness in interactive systems rather than
minimizing average waiting time — every process gets CPU time regularly,
which matters a lot for a system with a human waiting for a response, and
matters much less for a batch job where only total completion time is
measured.

Choosing the time quantum is a real trade-off: too large and Round Robin
degenerates toward FCFS (each process basically runs to completion within
its first quantum); too small and the overhead of context switching between
processes starts to dominate actual work — a common rule of thumb is that
80% of CPU bursts should be shorter than the time quantum.

## Priority Scheduling

Each process gets a priority number, and the scheduler always picks the
highest-priority ready process. Can be combined with either FCFS-style
non-preemptive scheduling or preemptive scheduling (a newly arriving
higher-priority process interrupts the current one). The major failure mode
is starvation — a low-priority process can wait indefinitely if
higher-priority processes keep arriving. The standard fix is aging:
gradually increase a waiting process's priority the longer it waits, which
guarantees it eventually becomes the highest priority in the system.

## Multilevel Feedback Queue

Multiple queues, each with its own priority and scheduling algorithm
(commonly Round Robin with an increasing time quantum at lower-priority
queues), with processes moving between queues based on observed behavior —
a process that uses its full time quantum repeatedly (CPU-bound) gets
demoted to a lower-priority, longer-quantum queue, while a process that
frequently gives up the CPU before its quantum expires (I/O-bound,
interactive) stays at a higher-priority, shorter-quantum queue. This is the
closest textbook approximation to what real general-purpose OS schedulers
actually do, since it adapts to process behavior rather than requiring
burst lengths or priorities to be known in advance.
