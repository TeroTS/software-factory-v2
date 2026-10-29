# Run the existing ticket-plan CLI when the planning package is invoked as a module.
from software_factory.planning import main

raise SystemExit(main())
