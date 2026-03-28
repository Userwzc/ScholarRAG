import { useState, useEffect, useCallback } from "react"
import { Link } from "react-router-dom"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { Plus, FileText, Trash2, Loader2, Upload, BookOpen, RefreshCw, AlertCircle, CheckCircle2, Clock } from "lucide-react"
import { Button } from "../components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card"
import { fetchPapers, deletePaper, uploadPaperAsync, getJobStatus, listJobs, retryJob, type IngestionJobListItem } from "../lib/api"
import { cn } from "../lib/utils"

type JobStatus = "pending" | "processing" | "completed" | "failed"

interface JobWithStatus extends IngestionJobListItem {
  filename?: string
}

function JobCard({ job, onRetry }: { job: JobWithStatus; onRetry: (jobId: string) => void }) {
  const statusConfig: Record<JobStatus, { icon: typeof Clock; color: string; bg: string; label: string }> = {
    pending: { icon: Clock, color: "text-muted-foreground", bg: "bg-secondary/50", label: "Queued" },
    processing: { icon: Loader2, color: "text-primary", bg: "bg-primary/10", label: "Processing" },
    completed: { icon: CheckCircle2, color: "text-green-600 dark:text-green-400", bg: "bg-green-500/10", label: "Completed" },
    failed: { icon: AlertCircle, color: "text-destructive", bg: "bg-destructive/10", label: "Failed" },
  }

  const config = statusConfig[job.status]
  const Icon = config.icon

  return (
    <Card className={cn("group card-hover", config.bg)}>
      <CardHeader className="pb-3">
        <div className="flex items-start gap-3">
          <div className={cn(
            "flex h-10 w-10 items-center justify-center rounded-xl border flex-shrink-0 transition-colors",
            config.bg,
            job.status === "processing" && "border-primary/30",
            job.status === "failed" && "border-destructive/30",
            job.status === "completed" && "border-green-500/30",
          )}>
            <Icon className={cn("h-5 w-5", config.color, job.status === "processing" && "animate-spin")} />
          </div>
          <div className="flex-1 min-w-0">
            <CardTitle className="text-base line-clamp-1 leading-snug">
              {job.filename || job.pdf_name || "Uploading..."}
            </CardTitle>
            <p className="text-xs text-muted-foreground mt-1">{config.label}</p>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {job.status === "processing" && (
          <div className="space-y-2">
            <div className="flex items-center justify-between text-xs">
              <span className="text-muted-foreground">{job.stage}</span>
              <span className="font-mono">{job.progress}%</span>
            </div>
            <div className="h-1.5 bg-secondary rounded-full overflow-hidden">
              <div 
                className="h-full bg-primary transition-all duration-300 rounded-full"
                style={{ width: `${job.progress}%` }}
              />
            </div>
          </div>
        )}
        {job.status === "failed" && (
          <div className="flex gap-2">
            <Button 
              variant="outline" 
              size="sm" 
              className="flex-1 rounded-xl"
              onClick={() => onRetry(job.job_id)}
            >
              <RefreshCw className="h-3 w-3 mr-1.5" />
              Retry
            </Button>
          </div>
        )}
        {job.status === "completed" && job.pdf_name && (
          <Button variant="outline" size="sm" className="w-full rounded-xl" asChild>
            <Link to={`/papers/${job.pdf_name}`}>View Paper</Link>
          </Button>
        )}
      </CardContent>
    </Card>
  )
}

export default function PapersPage() {
  const queryClient = useQueryClient()
  const [isUploading, setIsUploading] = useState(false)
  const [dragActive, setDragActive] = useState(false)
  const [activeJobs, setActiveJobs] = useState<Map<string, JobWithStatus>>(new Map())

  const { data: papers = [], isLoading } = useQuery({
    queryKey: ["papers"],
    queryFn: fetchPapers,
  })

  const { data: jobsData } = useQuery({
    queryKey: ["jobs"],
    queryFn: () => listJobs(20),
    refetchInterval: (query) => {
      // Only poll when there are active (pending/processing) jobs
      const jobs = query.state.data?.jobs || []
      const hasActiveJobs = jobs.some(
        (job: JobWithStatus) => job.status === "pending" || job.status === "processing"
      )
      return hasActiveJobs ? 5000 : false // Poll every 5s if active, otherwise stop
    },
  })

  const deleteMutation = useMutation({
    mutationFn: deletePaper,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["papers"] })
    },
  })

  const retryMutation = useMutation({
    mutationFn: retryJob,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["jobs"] })
    },
  })

  useEffect(() => {
    if (jobsData?.jobs) {
      setActiveJobs(prev => {
        const newJobs = new Map<string, JobWithStatus>()
        for (const job of jobsData.jobs) {
          if (job.status !== "completed" || prev.has(job.job_id)) {
            newJobs.set(job.job_id, job)
          }
        }
        return newJobs
      })
    }
  }, [jobsData])

  const pollJobStatus = useCallback(async (jobId: string, filename: string) => {
    const poll = async () => {
      try {
        const job = await getJobStatus(jobId)
        const existingJob = activeJobs.get(jobId)
        setActiveJobs(prev => {
          const next = new Map(prev)
          next.set(jobId, { 
            job_id: jobId,
            pdf_name: job.result?.pdf_name || existingJob?.pdf_name || "",
            status: job.status,
            stage: job.stage,
            progress: job.progress,
            retry_count: job.retry_count,
            created_at: job.created_at,
            updated_at: job.updated_at,
            filename,
          })
          return next
        })

        if (job.status === "processing") {
          setTimeout(poll, 1000)
        } else if (job.status === "completed") {
          queryClient.invalidateQueries({ queryKey: ["papers"] })
          setTimeout(() => {
            setActiveJobs(prev => {
              const next = new Map(prev)
              next.delete(jobId)
              return next
            })
          }, 3000)
        } else if (job.status === "failed") {
          queryClient.invalidateQueries({ queryKey: ["jobs"] })
        }
      } catch (error) {
        console.error("Failed to poll job status:", error)
      }
    }
    poll()
  }, [queryClient, activeJobs])

  const handleUpload = async (file: File) => {
    if (!file.name.toLowerCase().endsWith(".pdf")) {
      return
    }
    setIsUploading(true)
    try {
      const result = await uploadPaperAsync(file)
      setActiveJobs(prev => {
        const next = new Map(prev)
        next.set(result.job_id, {
          job_id: result.job_id,
          pdf_name: "",
          status: "pending",
          stage: "queued",
          progress: 0,
          retry_count: 0,
          created_at: Date.now(),
          updated_at: Date.now(),
          filename: file.name,
        })
        return next
      })
      pollJobStatus(result.job_id, file.name)
    } catch (error) {
      console.error("Upload failed:", error)
    } finally {
      setIsUploading(false)
    }
  }

  const handleRetry = async (jobId: string) => {
    try {
      await retryMutation.mutateAsync(jobId)
      const job = activeJobs.get(jobId)
      if (job) {
        pollJobStatus(jobId, job.filename || job.pdf_name)
      }
    } catch (error) {
      console.error("Retry failed:", error)
    }
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setDragActive(false)
    const file = e.dataTransfer.files[0]
    if (file) handleUpload(file)
  }

  const handleFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) handleUpload(file)
  }

  const inProgressJobs = Array.from(activeJobs.values()).filter(
    job => job.status === "pending" || job.status === "processing"
  )
  const failedJobs = Array.from(activeJobs.values()).filter(job => job.status === "failed")

  return (
    <div className="container mx-auto max-w-6xl px-4 py-8">
      <div className="flex items-center justify-between mb-8">
        <div className="space-y-1">
          <h1 className="text-3xl font-bold tracking-tight">Paper Library</h1>
          <p className="text-muted-foreground">
            Manage your uploaded academic papers
          </p>
        </div>
        <label className="cursor-pointer">
          <input
            type="file"
            accept=".pdf"
            className="hidden"
            onChange={handleFileInput}
            disabled={isUploading}
          />
          <Button asChild disabled={isUploading} size="lg">
            <span>
              {isUploading 
                ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> 
                : <Plus className="h-4 w-4 mr-2" />
              }
              Upload Paper
            </span>
          </Button>
        </label>
      </div>

      <div
        className={cn(
          "border-2 border-dashed rounded-2xl p-12 mb-8 text-center transition-all duration-300",
          dragActive 
            ? "border-primary bg-primary/5 scale-[1.01]" 
            : "border-border/60 hover:border-primary/40 hover:bg-accent/30"
        )}
        onDragOver={(e) => { e.preventDefault(); setDragActive(true) }}
        onDragLeave={() => setDragActive(false)}
        onDrop={handleDrop}
      >
        <div className="flex flex-col items-center gap-4">
          <div className={cn(
            "p-4 rounded-2xl transition-colors duration-300",
            dragActive ? "bg-primary/10" : "bg-secondary/50"
          )}>
            <Upload className={cn(
              "h-8 w-8 transition-colors duration-300",
              dragActive ? "text-primary" : "text-muted-foreground"
            )} />
          </div>
          <div>
            <p className="font-medium text-foreground">
              Drag and drop a PDF file here
            </p>
            <p className="text-sm text-muted-foreground mt-1">
              or click the Upload button above
            </p>
          </div>
        </div>
      </div>

      {(inProgressJobs.length > 0 || failedJobs.length > 0) && (
        <div className="mb-8">
          <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
            {inProgressJobs.length > 0 && (
              <Loader2 className="h-4 w-4 animate-spin text-primary" />
            )}
            {inProgressJobs.length > 0 ? "Processing" : "Failed Jobs"}
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
            {[...inProgressJobs, ...failedJobs].map((job) => (
              <JobCard key={job.job_id} job={job} onRetry={handleRetry} />
            ))}
          </div>
        </div>
      )}

      {isLoading ? (
        <div className="flex justify-center py-16">
          <div className="flex flex-col items-center gap-3">
            <Loader2 className="h-8 w-8 animate-spin text-primary" />
            <p className="text-sm text-muted-foreground">Loading papers...</p>
          </div>
        </div>
      ) : papers.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16">
          <div className="p-6 rounded-2xl bg-secondary/30 border border-border/30 mb-4">
            <BookOpen className="h-12 w-12 text-muted-foreground/50" />
          </div>
          <p className="text-muted-foreground font-medium">No papers yet</p>
          <p className="text-sm text-muted-foreground/70 mt-1">Upload your first paper to get started</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
          {papers.map((paper) => (
            <Card key={paper.pdf_name} className="group card-hover">
              <CardHeader className="pb-3">
                <div className="flex items-start gap-3">
                  <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/10 border border-primary/20 flex-shrink-0 group-hover:bg-primary/15 transition-colors">
                    <FileText className="h-5 w-5 text-primary" />
                  </div>
                  <CardTitle className="text-base line-clamp-2 leading-snug">
                    {paper.title}
                  </CardTitle>
                </div>
              </CardHeader>
              <CardContent className="space-y-4">
                <p className="text-sm text-muted-foreground line-clamp-2 leading-relaxed">
                  {paper.authors || "Unknown authors"}
                </p>
                <div className="flex items-center justify-between text-xs">
                  <span className="flex items-center gap-1.5 text-muted-foreground bg-secondary/50 px-2 py-1 rounded-lg">
                    <BookOpen className="h-3 w-3" />
                    {paper.chunk_count} chunks
                  </span>
                  <span className="text-muted-foreground/60 font-mono">
                    {paper.pdf_name}.pdf
                  </span>
                </div>
                <div className="flex gap-2 pt-2">
                  <Button variant="outline" size="sm" className="flex-1 rounded-xl" asChild>
                    <Link to={`/papers/${paper.pdf_name}`}>View Details</Link>
                  </Button>
                  <Button variant="ghost" size="sm" className="rounded-xl text-muted-foreground hover:text-destructive hover:bg-destructive/10" asChild>
                    <Link to={`/papers/${paper.pdf_name}/read`}>Read</Link>
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="rounded-xl text-muted-foreground hover:text-destructive hover:bg-destructive/10"
                    onClick={() => {
                      if (confirm(`Delete "${paper.title}"?`)) {
                        deleteMutation.mutate(paper.pdf_name)
                      }
                    }}
                    disabled={deleteMutation.isPending}
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}
