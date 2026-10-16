// Independently authored consumer requirements for the actual native graph scene API.
namespace GraphSceneTarget {
  import G = ArchkeelGraphProtocol;
  import P = ArchkeelGraphSceneProtocol;
  interface RequiredScene {
    nodes: {id: string; kind: G.EntityKind; entity: P.Entity; sourceGraph: P.Graph}[];
    edges: {id: string; relationshipKind: G.RelationshipKind; state: P.EdgeState}[];
    owner: string | null;
    componentOverview: boolean;
  }
  const api = ArchkeelGraphScene.create({});
  const projection: (context: P.Context, options: P.Options) => RequiredScene = api.projectArchitectureScene;
  const members: (entity: P.Entity, includeName?: boolean) => string = api.member;
  const entities: (graph: P.Graph) => P.Entity[] = api.entities;
  void projection; void members; void entities;
}
