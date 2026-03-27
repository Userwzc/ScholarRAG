import { useState } from "react"
import { useParams, useNavigate, Link } from "react-router-dom"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { ArrowLeft, Trash2, Loader2, FileText, Image, Table, BookOpen, History, RefreshCw, Check } from "lucide-react"
import { Button } from "../components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card"
import { Input } from "../components/ui/input"
import { fetchPaper, fetchChunks, deletePaper, fetchVersions, reindexPaper } from "../lib/api"
import { cn } from "../lib/utils"

export default function PaperDetailPage() {
  const { pdfName } = useParams<{ pdfName: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [page, setPage] = useState(1)
  const [searchQuery, setSearchQuery] = useState("")
  const [typeFilter, setTypeFilter] = useState<string>("")

  const { data: paper, isLoading: paperLoading } = useQuery({
    queryKey: ["paper", pdfName],
    queryFn: () => fetchPaper(pdfName!),
    enabled: !!pdfName,
  })

  const { data: chunksData, isLoading: chunksLoading } = useQuery({
    queryKey: ["chunks", pdfName, page, typeFilter],
    queryFn: () => fetchChunks(pdfName!, page, 20, typeFilter || undefined),
    enabled: !!pdfName,
  })

  const { data: versions, isLoading: versionsLoading } = useQuery({
    queryKey: ["versions", pdfName],
    queryFn: () => fetchVersions(pdfName!),
    enabled: !!pdfName,
  })

  const reindexMutation = useMutation({
    mutationFn: () => reindexPaper(pdfName!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["versions", pdfName] })
      queryClient.invalidateQueries({ queryKey: ["chunks", pdfName] })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: () => deletePaper(pdfName!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["papers"] })
      navigate("/papers")
    },
  })

  if (paperLoading) {
    return (
      <div className="flex justify-center py-16">
        <div className="flex flex-col items-center gap-3">
          <Loader2 className="h-8 w-8 animate-spin text-primary" />
          <p className="text-sm text-muted-foreground">Loading paper...</p>
        </div>
      </div>
    )
  }

  if (!paper) {
    return (
      <div className="container mx-auto max-w-4xl px-4 py-8">
        <div className="text-center py-16">
          <FileText className="h-12 w-12 mx-auto mb-4 text-muted-foreground/50" />
          <p className="text-muted-foreground">Paper not found</p>
        </div>
      </div>
    )
  }

  const filteredChunks = chunksData?.chunks.filter((chunk) =>
    searchQuery ? chunk.content.toLowerCase().includes(searchQuery.toLowerCase()) : true
  ) || []

  const totalPages = chunksData ? Math.ceil(chunksData.total / chunksData.limit) : 1

  return (
    <div className="container mx-auto max-w-4xl px-4 py-8">
      <Button variant="ghost" asChild className="mb-6 rounded-xl">
        <Link to="/papers">
          <ArrowLeft className="h-4 w-4 mr-2" />
          Back to Papers
        </Link>
      </Button>

      <Card className="mb-8 overflow-hidden">
        <div className="h-2 gradient-primary" />
        <CardHeader className="pb-4">
          <CardTitle className="text-2xl leading-snug">{paper.title}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-muted-foreground leading-relaxed">{paper.authors || "Unknown authors"}</p>
          <div className="flex items-center gap-4 text-sm text-muted-foreground">
            <span className="flex items-center gap-1.5 bg-secondary/50 px-3 py-1 rounded-lg">
              <FileText className="h-3.5 w-3.5" />
              {paper.pdf_name}.pdf
            </span>
            <span className="flex items-center gap-1.5 bg-secondary/50 px-3 py-1 rounded-lg">
              <BookOpen className="h-3.5 w-3.5" />
              {paper.chunk_count} chunks
            </span>
          </div>
          <div className="flex gap-3 pt-2">
            <Button
              size="default"
              onClick={() => navigate(`/papers/${pdfName}/read`)}
            >
              <BookOpen className="h-4 w-4 mr-2" />
              Read Paper
            </Button>
            <Button
              variant="outline"
              size="default"
              onClick={() => {
                if (confirm(`Delete "${paper.title}"?`)) {
                  deleteMutation.mutate()
                }
              }}
              disabled={deleteMutation.isPending}
              className="text-destructive hover:bg-destructive/10 hover:border-destructive/30"
            >
              <Trash2 className="h-4 w-4 mr-2" />
              Delete Paper
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card className="mb-8 overflow-hidden">
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <CardTitle className="text-lg flex items-center gap-2">
              <History className="h-5 w-5" />
              Version History
            </CardTitle>
            <Button
              variant="outline"
              size="sm"
              onClick={() => reindexMutation.mutate()}
              disabled={reindexMutation.isPending}
              className="rounded-xl"
            >
              {reindexMutation.isPending ? (
                <Loader2 className="h-4 w-4 mr-1.5 animate-spin" />
              ) : (
                <RefreshCw className="h-4 w-4 mr-1.5" />
              )}
              重新索引
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {versionsLoading ? (
            <div className="flex justify-center py-4">
              <Loader2 className="h-5 w-5 animate-spin text-primary" />
            </div>
          ) : versions && versions.length > 0 ? (
            <div className="space-y-2">
              {versions.map((version) => (
                <div
                  key={version.id}
                  className={cn(
                    "flex items-center justify-between p-3 rounded-xl transition-colors",
                    version.is_current
                      ? "bg-primary/10 border border-primary/20"
                      : "bg-secondary/30 hover:bg-secondary/50"
                  )}
                >
                  <div className="flex items-center gap-3">
                    <div className={cn(
                      "flex items-center justify-center h-8 w-8 rounded-lg text-sm font-medium",
                      version.is_current
                        ? "bg-primary/20 text-primary"
                        : "bg-secondary text-muted-foreground"
                    )}>
                      v{version.version_number}
                    </div>
                    <div>
                      <p className="text-sm font-medium">
                        Version {version.version_number}
                        {version.is_current && (
                          <span className="ml-2 text-xs text-primary font-normal flex items-center gap-1 inline-flex">
                            <Check className="h-3 w-3" />
                            当前版本
                          </span>
                        )}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        {new Date(version.created_at * 1000).toLocaleString()}
                      </p>
                    </div>
                  </div>
                  <div className="text-xs text-muted-foreground font-mono">
                    {version.source_hash.slice(0, 8)}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground text-center py-4">
              No version history available
            </p>
          )}
        </CardContent>
      </Card>

      <div className="flex gap-4 mb-6">
        <Input
          placeholder="Search chunks..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="flex-1"
        />
        <select
          className="flex h-10 rounded-xl border-2 border-border/50 bg-card/50 backdrop-blur-sm px-4 py-2 text-sm hover:border-primary/30 focus:outline-none focus:border-primary focus:ring-4 focus:ring-primary/10 transition-all"
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value)}
        >
          <option value="">All Types</option>
          <option value="text">Text</option>
          <option value="image">Image</option>
          <option value="table">Table</option>
        </select>
      </div>

      {chunksLoading ? (
        <div className="flex justify-center py-12">
          <Loader2 className="h-6 w-6 animate-spin text-primary" />
        </div>
      ) : (
        <>
          <div className="space-y-4">
            {filteredChunks.map((chunk, idx) => (
              <Card key={chunk.id || idx} className="card-hover">
                <CardHeader className="pb-2">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <div className={cn(
                        "flex items-center justify-center h-7 w-7 rounded-lg",
                        chunk.chunk_type === "image" ? "bg-purple-500/10 text-purple-600" :
                        chunk.chunk_type === "table" ? "bg-emerald-500/10 text-emerald-600" :
                        "bg-primary/10 text-primary"
                      )}>
                        {chunk.chunk_type === "image" ? (
                          <Image className="h-4 w-4" />
                        ) : chunk.chunk_type === "table" ? (
                          <Table className="h-4 w-4" />
                        ) : (
                          <FileText className="h-4 w-4" />
                        )}
                      </div>
                      <span className="text-sm font-medium capitalize">{chunk.chunk_type}</span>
                      {chunk.page_idx !== undefined && (
                        <span className="text-sm text-muted-foreground bg-secondary/50 px-2 py-0.5 rounded-md">
                          Page {chunk.page_idx}
                        </span>
                      )}
                    </div>
                    {chunk.heading && (
                      <span className="text-sm text-muted-foreground truncate max-w-[200px]">{chunk.heading}</span>
                    )}
                  </div>
                </CardHeader>
                <CardContent>
                  <p className="text-sm whitespace-pre-wrap leading-relaxed">{chunk.content}</p>
                </CardContent>
              </Card>
            ))}
          </div>

          {totalPages > 1 && (
            <div className="flex justify-center gap-3 mt-8">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page === 1}
                className="rounded-xl"
              >
                Previous
              </Button>
              <span className="flex items-center px-4 text-sm text-muted-foreground bg-secondary/30 rounded-xl">
                Page {page} of {totalPages}
              </span>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page === totalPages}
                className="rounded-xl"
              >
                Next
              </Button>
            </div>
          )}
        </>
      )}
    </div>
  )
}
