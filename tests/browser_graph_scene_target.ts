// Independently authored consumer requirements for the actual native graph scene API.
namespace GraphSceneTarget {
  import G = ArchkeelGraphProtocol;
  import P = ArchkeelGraphSceneProtocol;
  interface RequiredScene {
    nodes: {id: string; kind: G.EntityKind; entity: P.Entity; sourceGraph: P.Graph}[];
    edges: {id: string; kind: P.SceneEdgeKind; relationshipKind: G.RelationshipKind; state: P.EdgeState}[];
    owner: string | null;
    componentOverview: boolean;
  }
  const api = ArchkeelGraphScene.create({});
  const projection: (context: P.Context, options?: {
    viewMode?: P.ViewMode; directChildren?: boolean;
  }) => RequiredScene = api.projectArchitectureScene;
  const members: (entity: P.Entity, includeName?: boolean) => string = api.member;
  const entities: (graph: P.Graph) => P.Entity[] = api.entities;
  const projectionMode: (view: P.ViewMode) =>
    P.ViewMode.DIAGRAM | P.ViewMode.TARGET | P.ViewMode.DIFF = P.projectViewMode;
  const evidenceViews: P.Options[] = [
    {viewMode:P.ViewMode.ACTUAL}, {viewMode:P.ViewMode.STRUCTURE}, {viewMode:P.ViewMode.REVIEW},
  ];
  void projection; void members; void entities; void projectionMode; void evidenceViews;
}

namespace AtlasDeviationTarget {
  import G = ArchkeelGraphProtocol;
  const api = ArchkeelAtlasDeviations.create([]);
  const unused: (levelId: string | null) => readonly {
    id: string; kind: G.AtlasDeviationKind; source_id: string; target_id: string;
    level_id: string | null;
  }[] = api.unused;
  const undeclared: (levelId: string | null, source: string, target: string) => boolean = api.isUndeclared;
  void unused; void undeclared;
}
