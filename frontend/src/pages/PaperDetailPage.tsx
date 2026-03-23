import { useState } from "react"
import { useParams, useNavigate, Link } from "react-router-dom"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { ArrowLeft, Trash2, Loader2, FileText, Image, Table, BookOpen } from "lucide-react"
import { Button } from "../components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card"
import { Input } from "../components/ui/input"
import { fetchPaper, fetchChunks, deletePaper } from "../lib/api"

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

  const deleteMutation = useMutation({
    mutationFn: () => deletePaper(pdfName!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["papers"] })
      navigate("/papers")
    },
  })

  if (paperLoading) {
    return (
      <div className="flex justify-center py-12">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (!paper) {
    return (
      <div className="container mx-auto max-w-4xl px-4 py-8">
        <p>Paper not found</p>
      </div>
    )
  }

  const filteredChunks = chunksData?.chunks.filter((chunk) =>
    searchQuery ? chunk.content.toLowerCase().includes(searchQuery.toLowerCase()) : true
  ) || []

  const totalPages = chunksData ? Math.ceil(chunksData.total / chunksData.limit) : 1

  return (
    <div className="container mx-auto max-w-4xl px-4 py-8">
      <Button variant="ghost" asChild className="mb-4">
        <Link to="/papers">
          <ArrowLeft className="h-4 w-4 mr-2" />
          Back to Papers
        </Link>
      </Button>

      <Card className="mb-6">
        <CardHeader>
          <CardTitle className="text-2xl">{paper.title}</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-muted-foreground mb-2">{paper.authors || "Unknown authors"}</p>
          <div className="flex items-center gap-4 text-sm text-muted-foreground">
            <span>File: {paper.pdf_name}.pdf</span>
            <span>Chunks: {paper.chunk_count}</span>
          </div>
          <div className="flex gap-2 mt-4">
            <Button
              variant="default"
              size="sm"
              onClick={() => navigate(`/papers/${pdfName}/read`)}
            >
              <BookOpen className="h-4 w-4 mr-2" />
              Read Paper
            </Button>
            <Button
              variant="destructive"
              size="sm"
              onClick={() => {
                if (confirm(`Delete "${paper.title}"?`)) {
                  deleteMutation.mutate()
                }
              }}
              disabled={deleteMutation.isPending}
            >
              <Trash2 className="h-4 w-4 mr-2" />
              Delete Paper
            </Button>
          </div>
        </CardContent>
      </Card>

      <div className="flex gap-4 mb-4">
        <Input
          placeholder="Search chunks..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="flex-1"
        />
        <select
          className="flex h-10 rounded-md border border-input bg-background px-3 py-2 text-sm"
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
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      ) : (
        <>
          <div className="space-y-4">
            {filteredChunks.map((chunk, idx) => (
              <Card key={chunk.id || idx}>
                <CardHeader className="pb-2">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      {chunk.chunk_type === "image" ? (
                        <Image className="h-4 w-4" />
                      ) : chunk.chunk_type === "table" ? (
                        <Table className="h-4 w-4" />
                      ) : (
                        <FileText className="h-4 w-4" />
                      )}
                      <span className="text-sm font-medium capitalize">{chunk.chunk_type}</span>
                      {chunk.page_idx !== undefined && (
                        <span className="text-sm text-muted-foreground">Page {chunk.page_idx}</span>
                      )}
                    </div>
                    {chunk.heading && (
                      <span className="text-sm text-muted-foreground">{chunk.heading}</span>
                    )}
                  </div>
                </CardHeader>
                <CardContent>
                  <p className="text-sm whitespace-pre-wrap">{chunk.content}</p>
                </CardContent>
              </Card>
            ))}
          </div>

          {totalPages > 1 && (
            <div className="flex justify-center gap-2 mt-6">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page === 1}
              >
                Previous
              </Button>
              <span className="flex items-center px-4 text-sm">
                Page {page} of {totalPages}
              </span>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page === totalPages}
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
