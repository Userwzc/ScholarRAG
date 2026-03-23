import { useState } from "react"
import { Link } from "react-router-dom"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { Plus, FileText, Trash2, Loader2, Upload, BookOpen } from "lucide-react"
import { Button } from "../components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card"
import { fetchPapers, deletePaper, uploadPaper } from "../lib/api"
import { cn } from "../lib/utils"

export default function PapersPage() {
  const queryClient = useQueryClient()
  const [isUploading, setIsUploading] = useState(false)
  const [dragActive, setDragActive] = useState(false)

  const { data: papers = [], isLoading } = useQuery({
    queryKey: ["papers"],
    queryFn: fetchPapers,
  })

  const deleteMutation = useMutation({
    mutationFn: deletePaper,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["papers"] })
    },
  })

  const handleUpload = async (file: File) => {
    if (!file.name.toLowerCase().endsWith(".pdf")) {
      alert("Only PDF files are supported")
      return
    }
    setIsUploading(true)
    try {
      await uploadPaper(file)
      queryClient.invalidateQueries({ queryKey: ["papers"] })
    } catch (error) {
      console.error("Upload failed:", error)
      alert("Upload failed. Please try again.")
    } finally {
      setIsUploading(false)
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
