import os
import os.path
import tempfile
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path
from textwrap import indent

import pandas as pd
import scanpy as sc
from anndata import AnnData

from ..io._convert_anndata import from_airr_cells
from ..io._datastructures import AirrCell
from ..io._io import _infer_locus_from_gene_names, _IOLogger
from ..pp import index_chains
from ..util import _doc_params, _read_to_str, tqdm

HERE = Path(__file__).parent
from os import PathLike
from textwrap import dedent
from typing import cast

import mudata
import pooch
from mudata import MuData
from scanpy import logging

from .. import __version__
from ..util import tqdm

_FIGSHARE = pooch.create(
    path=pooch.os_cache("scirpy"),
    base_url="doi:10.6084/m9.figshare.22249894.v1",
    version=__version__,
    version_dev="main",
    env="SCIRPY_DATA_DIR",
    registry={
        "wu2020.h5mu": "md5:ed30d9c1c44cae544f4c080a2451118b",
        "wu2020_3k.h5mu": "md5:12c57c790f8a403751304c9de5a18cbf",
        "maynard2020.h5mu": "md5:da64ac62e3e92c80eaf0e8eef6537ac7",
    },
)
_POOCH_INFO = dedent(
    """\
    .. note::
        Scirpy example datasets are managed through `Pooch <https://github.com/fatiando/pooch>`_. 

        By default, the dataset will be downloaded into your operating system's default
        cache directory (See :func:`pooch.os_cache` for more details). If it has already been
        downloaded, it will be retrieved from the cache. 

        You can override the default cache dir by setting the `SCIRPY_DATA_DIR` environment variable
        to a path of your preference. 
    """
)


@_doc_params(
    processing_code=indent(_read_to_str(HERE / "_processing_scripts/wu2020.py"), "   "),
    pooch_info=_POOCH_INFO,
)
def wu2020() -> MuData:
    """\
    Return the dataset from :cite:`Wu2020` as MuData object.

    140k cells, of which 100k have TCRs.

    {pooch_info}

    This is how the dataset was processed:

    .. code-block:: python

    {processing_code}
    """
    fname = cast(PathLike, _FIGSHARE.fetch("wu2020.h5mu", progressbar=True))
    return mudata.read_h5mu(fname)


@_doc_params(
    processing_code=indent(
        _read_to_str(HERE / "_processing_scripts/wu2020_3k.py"), "   "
    ),
    pooch_info=_POOCH_INFO,
)
def wu2020_3k() -> MuData:
    """\
    Return the dataset from :cite:`Wu2020` as AnnData object, downsampled
    to 3000 TCR-containing cells.

    {pooch_info}

    This is how the dataset was processed:

    .. code-block:: python

    {processing_code}
    """
    fname = cast(PathLike, _FIGSHARE.fetch("wu2020_3k.h5mu", progressbar=True))
    return mudata.read_h5mu(fname)


@_doc_params(
    processing_code=indent(
        _read_to_str(HERE / "_processing_scripts/maynard2020.py"), "   "
    ),
    pooch_info=_POOCH_INFO,
)
def maynard2020() -> MuData:
    """\
    Return the dataset from :cite:`Maynard2020` as AnnData object.

    21k cells from NSCLC profiled with Smart-seq2, of which 3,500 have :term:`TCRs<TCR>`
    and 1,500 have :term:`BCRs<BCR>`.

    {pooch_info}

    The raw FASTQ files have been obtained from `PRJNA591860 <https://www.ebi.ac.uk/ena/browser/view/PRJNA591860>`__
    and processed using the nf-core `RNA-seq pipeline <https://github.com/nf-core/rnaseq>`_ to obtain 
    gene expression and TraCeR/BraCeR to reconstruct receptors. 

    The processed files have been imported and transformed into an :class:`anndata.AnnData`
    object using the following script:

    .. code-block:: python

    {processing_code}
    """
    fname = cast(PathLike, _FIGSHARE.fetch("maynard2020.h5mu", progressbar=True))
    return mudata.read_h5mu(fname)


def vdjdb(cached: bool = True, *, cache_path="data/vdjdb.h5ad") -> AnnData:
    """\
    Download VDJdb and process it into an AnnData object.

    `VDJdb <https://vdjdb.cdr3.net/>`_ :cite:`vdjdb` is a curated database of
    T-cell receptor (TCR) sequences with known antigen specificities.

    Parameters
    ----------
    cached
        If `True`, attempt to read from the `data` directory before downloading
    cache_path
        Location where the h5ad object will be saved

    Returns
    -------
    An anndata object containing all entries from VDJDB in `obsm["airr"]`.
    Each entry is represented as if it was a cell, but without gene expression.
    Metadata is stored in `adata.uns["DB"]`.
    """
    if cached:
        try:
            return sc.read_h5ad(cache_path)
        except OSError:
            pass

    logging.info("Downloading latest version of VDJDB")
    with urllib.request.urlopen(
        "https://raw.githubusercontent.com/antigenomics/vdjdb-db/master/latest-version.txt"
    ) as url:
        latest_versions = url.read().decode().split()
    url = latest_versions[0]

    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        urllib.request.urlretrieve(url, d / "vdjdb.tar.gz")
        with zipfile.ZipFile(d / "vdjdb.tar.gz") as zf:
            zf.extractall(d)
        df = pd.read_csv(d / "vdjdb_full.txt", sep="\t")

    tcr_cells = []
    for idx, row in tqdm(
        df.iterrows(), total=df.shape[0], desc="Processing VDJDB entries"
    ):
        cell = AirrCell(cell_id=str(idx))
        if not pd.isnull(row["cdr3.alpha"]):
            alpha_chain = AirrCell.empty_chain_dict()
            alpha_chain.update(
                {
                    "locus": "TRA",
                    "junction_aa": row["cdr3.alpha"],
                    "v_call": row["v.alpha"],
                    "j_call": row["j.alpha"],
                    "consensus_count": 0,
                    "productive": True,
                }
            )
            cell.add_chain(alpha_chain)

        if not pd.isnull(row["cdr3.beta"]):
            beta_chain = AirrCell.empty_chain_dict()
            beta_chain.update(
                {
                    "locus": "TRB",
                    "junction_aa": row["cdr3.beta"],
                    "v_call": row["v.beta"],
                    "d_call": row["d.beta"],
                    "j_call": row["j.beta"],
                    "consensus_count": 0,
                    "productive": True,
                }
            )
            cell.add_chain(beta_chain)

        INCLUDE_CELL_METADATA_FIELDS = [
            "species",
            "mhc.a",
            "mhc.b",
            "mhc.class",
            "antigen.epitope",
            "antigen.gene",
            "antigen.species",
            "reference.id",
            "method.identification",
            "method.frequency",
            "method.singlecell",
            "method.sequencing",
            "method.verification",
            "meta.study.id",
            "meta.cell.subset",
            "meta.subject.cohort",
            "meta.subject.id",
            "meta.replica.id",
            "meta.clone.id",
            "meta.epitope.id",
            "meta.tissue",
            "meta.donor.MHC",
            "meta.donor.MHC.method",
            "meta.structure.id",
            "vdjdb.score",
        ]
        for f in INCLUDE_CELL_METADATA_FIELDS:
            cell[f] = row[f]
        tcr_cells.append(cell)

    logging.info("Converting to AnnData object")
    adata = from_airr_cells(tcr_cells)
    index_chains(adata)

    adata.uns["DB"] = {"name": "VDJDB", "date_downloaded": datetime.now().isoformat()}

    # store cache
    os.makedirs(os.path.dirname(os.path.abspath(cache_path)), exist_ok=True)
    adata.write_h5ad(cast(os.PathLike, cache_path))

    return adata


def iedb(cached: bool = True, *, cache_path="data/iedb.h5ad") -> AnnData:
    """\
    Download IEBD v3 and process it into an AnnData object.

    :cite:`iedb` is a curated database of
    T-cell receptor (TCR) sequences with known antigen specificities.

    Parameters
    ----------
    cached
        If `True`, attempt to read from the `data` directory before downloading
    cache_path
        Location where the h5ad object will be saved

    Returns
    -------
    An anndata object containing all entries from IEDB in `obsm["airr"]`.
    Each entry is represented as if it was a cell, but without gene expression.
    Metadata is stored in `adata.uns["DB"]`.
    """
    if cached:
        try:
            return sc.read_h5ad(cache_path)
        except OSError:
            pass

    logger = _IOLogger()
    iedb_df = pd.read_csv(
        "https://www.iedb.org/downloader.php?file_name=doc/receptor_full_v3.zip",
        index_col=None,
        sep=",",
        na_values=["None"],
        true_values=["True"],
        low_memory=False,
    )

    iedb_df = iedb_df.drop_duplicates()
    iedb_df = iedb_df.drop_duplicates(
        [
            "Chain 1 CDR3 Curated",
            "Chain 2 CDR3 Curated",
            "Organism",
            "Antigen",
            "Response Type",
            "Chain 1 Type",
            "Chain 2 Type",
        ]
    )

    # If no curated CDR3 sequence or V/D/J gene is available, the calculated one is used.
    def replace_curated(input_1, input_2):
        calculated_1 = input_1.replace("Curated", "Calculated")
        iedb_df.loc[iedb_df[input_1].isna(), input_1] = iedb_df[calculated_1]
        iedb_df[input_1] = iedb_df[input_1].str.upper()
        calculated_2 = input_2.replace("Curated", "Calculated")
        iedb_df.loc[iedb_df[input_2].isna(), input_2] = iedb_df[calculated_2]
        iedb_df[input_2] = iedb_df[input_2].str.upper()

    replace_curated("Chain 1 CDR3 Curated", "Chain 2 CDR3 Curated")
    replace_curated("Curated Chain 1 V Gene", "Curated Chain 2 V Gene")
    replace_curated("Curated Chain 1 D Gene", "Curated Chain 2 D Gene")
    replace_curated("Curated Chain 1 J Gene", "Curated Chain 2 J Gene")

    iedb_df["cell_id"] = iedb_df.reset_index(drop=True).index

    accepted_chains = ["alpha", "beta", "heavy", "light", "gamma", "delta"]
    iedb_df = iedb_df[
        (iedb_df["Chain 1 Type"].isin(accepted_chains))
        & (iedb_df["Chain 2 Type"].isin(accepted_chains))
    ]

    receptor_dict = {
        "alpha": "TRA",
        "beta": "TRB",
        "heavy": "IGH",
        # IEDB does not distinguish between lambda and kappa
        "light": None,
        "gamma": "TRG",
        "delta": "TRD",
    }

    tcr_cells = []
    for _, row in iedb_df.iterrows():
        cell = AirrCell(cell_id=row["cell_id"], logger=logger)
        chain1 = AirrCell.empty_chain_dict()
        chain2 = AirrCell.empty_chain_dict()
        cell["Receptor ID"] = row["Receptor ID"]
        cell["Antigen"] = row["Antigen"]
        cell["Organism"] = row["Organism"]
        cell["Response Type"] = row["Response Type"]
        cell["Reference IRI"] = row["Reference IRI"]
        cell["Epitope IRI"] = row["Epitope IRI"]
        chain1.update(
            {
                "locus": receptor_dict[row["Chain 1 Type"]],
                "junction_aa": row["Chain 1 CDR3 Curated"],
                "junction": None,
                "consensus_count": None,
                "v_call": row["Curated Chain 1 V Gene"],
                "d_call": None,
                "j_call": row["Curated Chain 1 J Gene"],
                "productive": True,
            }
        )
        chain2.update(
            {
                "locus": receptor_dict[row["Chain 2 Type"]],
                "junction_aa": row["Chain 2 CDR3 Curated"],
                "junction": None,
                "consensus_count": None,
                "v_call": row["Curated Chain 2 V Gene"],
                "d_call": row["Curated Chain 2 D Gene"],
                "j_call": row["Curated Chain 2 J Gene"],
                "productive": True,
            }
        )
        for chain_dict in [chain1, chain2]:
            # Since IEDB does not distinguish between lambda and kappa light chains, we need
            # to call them from the gene names
            if chain_dict["locus"] is None:
                chain_dict["locus"] = _infer_locus_from_gene_names(
                    chain_dict, keys=("v_call", "d_call", "j_call")
                )
            cell.add_chain(chain_dict)

        tcr_cells.append(cell)

    logging.info("Converting to AnnData object")
    iedb = from_airr_cells(tcr_cells)
    iedb_df = iedb_df.set_index(iedb.obs.index)

    iedb.uns["DB"] = {"name": "IEDB", "date_downloaded": datetime.now().isoformat()}
    index_chains(iedb)

    # store cache
    os.makedirs(os.path.dirname(os.path.abspath(cache_path)), exist_ok=True)
    iedb.write_h5ad(cast(os.PathLike, cache_path))

    return iedb
